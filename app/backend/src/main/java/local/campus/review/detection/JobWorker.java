package local.campus.review.detection;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.common.*;
import local.campus.review.reference.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.scheduling.annotation.Scheduled;
import javax.sql.DataSource;
import java.util.*;

@Component
public class JobWorker {
    private static class WaitingService extends RuntimeException {}
    public record JobOutcome(String status,String jobId){}
    private final JdbcTemplate db;private final DataSource source;private final ObjectMapper json;
    private final DetectorClient client;private final DetectionService detection;private final AttemptRepository attempts;
    private final LibraryGenerationService libraries;private final ReferenceProcessor references;
    private final String owner=UUID.randomUUID().toString();private final RecoveryService recovery;
    private final local.campus.review.workbench.ReleaseService releases;
    public JobWorker(JdbcTemplate db,DataSource source,ObjectMapper json,DetectorClient client,DetectionService detection,AttemptRepository attempts,LibraryGenerationService libraries,ReferenceProcessor references,RecoveryService recovery,local.campus.review.workbench.ReleaseService releases){this.db=db;this.source=source;this.json=json;this.client=client;this.detection=detection;this.attempts=attempts;this.libraries=libraries;this.references=references;this.recovery=recovery;this.releases=releases;}
    @Scheduled(fixedDelay=2000) public void poll(){if("true".equalsIgnoreCase(System.getenv("CAMPUS_WORKER_ENABLED")))runOne();}
    public boolean claim(String id,String run){return db.update("UPDATE background_job SET status='RUNNING',owner_run_id=?,started_at=UTC_TIMESTAMP(3),error_code=NULL WHERE id=? AND status IN ('QUEUED','WAITING_SERVICE')",run,id)==1;}
    public JobOutcome runOne(){
        if(!recovery.recoverPreviousRun(owner))return new JobOutcome("WAITING_SERVICE",null);
        // The advisory lock is held on this physical connection across model calls.
        // It serializes workers without keeping a business transaction open.
        try(var connection=source.getConnection();var lock=connection.prepareStatement("SELECT GET_LOCK(?,0)")){
            String lockName=connection.getCatalog()+":worker";lock.setString(1,lockName);
            try(var result=lock.executeQuery()){if(!result.next() || result.getInt(1)!=1)return new JobOutcome("WORKER_BUSY",null);}
            try{
                var rows=db.queryForList("SELECT * FROM background_job WHERE status IN ('QUEUED','WAITING_SERVICE') ORDER BY id LIMIT 1");
                if(rows.isEmpty())return new JobOutcome("IDLE",null);
                var job=rows.getFirst();String id=job.get("id").toString();var main=client.health(false);var ocr=client.health(true);
                if(!main.path("ready").asBoolean() || main.path("busy").asBoolean() || ocr.path("busy").asBoolean()){
                    db.update("UPDATE background_job SET status='WAITING_SERVICE' WHERE id=? AND status IN ('QUEUED','WAITING_SERVICE')",id);markWaiting(job);return new JobOutcome("WAITING_SERVICE",id);
                }
                if(!claim(id,owner))return new JobOutcome("CLAIM_LOST",id);
                try{
                    switch(job.get("kind").toString()){
                        case "PREPARE_REFERENCE"->{var requested=new HashSet<String>();JsonSupport.parse(json,job.get("payload_json").toString()).path("failedPartKeys").forEach(part->requested.add(part.asText()));references.prepare(job.get("reference_revision_id").toString(),ocr,requested);}
                        case "REFRESH_LIBRARY"->references.refresh();
                        case "DETECT_BATCH"->runBatch(job.get("batch_id").toString(),null,main,ocr);
                        case "RETRY_ITEM"->{String item=job.get("item_id").toString();runBatch(db.queryForObject("SELECT batch_id FROM detection_item WHERE id=?",String.class,item),item,main,ocr);}
                        default->throw new DetectorClient.DetectorFailure("UNKNOWN_JOB_KIND");
                    }
                    db.update("UPDATE background_job SET status='COMPLETED',finished_at=UTC_TIMESTAMP(3) WHERE id=? AND owner_run_id=? AND status='RUNNING'",id,owner);
                    return new JobOutcome("COMPLETED",id);
                }catch(WaitingService e){db.update("UPDATE background_job SET status='WAITING_SERVICE' WHERE id=? AND owner_run_id=? AND status='RUNNING'",id,owner);markWaiting(job);return new JobOutcome("WAITING_SERVICE",id);
                }catch(Exception e){String code=e instanceof DetectorClient.DetectorFailure failure?failure.code:e instanceof ApiException api?api.code:"JOB_FAILED";
                    if("PREPARE_REFERENCE".equals(job.get("kind")))db.update("UPDATE reference_revision SET processing_status='FAILED' WHERE id=?",job.get("reference_revision_id"));
                    db.update("UPDATE background_job SET status='FAILED',error_code=?,finished_at=UTC_TIMESTAMP(3) WHERE id=? AND owner_run_id=? AND status='RUNNING'",code,id,owner);return new JobOutcome("FAILED",id);}
            }finally{try(var release=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){release.setString(1,lockName);release.execute();}}
        }catch(Exception e){throw new IllegalStateException("Queue database operation failed",e);}
    }
    private void markWaiting(Map<String,Object> job){
        Object batch=job.get("batch_id");if(batch==null && job.get("item_id")!=null)batch=db.queryForObject("SELECT batch_id FROM detection_item WHERE id=?",String.class,job.get("item_id"));
        if(batch!=null)db.update("UPDATE detection_batch SET status='WAITING_SERVICE' WHERE id=? AND cancelled_at IS NULL",batch);
    }
    private void runBatch(String batchId,String onlyItem,JsonNode main,JsonNode ocr){
        var batch=db.queryForMap("SELECT b.*,v.manuscript_id,v.plain_text FROM detection_batch b JOIN submission_version v ON v.id=b.submission_version_id WHERE b.id=?",batchId);
        if(batch.get("cancelled_at")!=null){db.update("UPDATE detection_item SET status='CANCELLED',updated_at=UTC_TIMESTAMP(3) WHERE batch_id=? AND status='QUEUED'",batchId);detection.finish(batchId);return;}
        JsonNode pipeline;
        if(batch.get("pipeline_manifest_json")==null){
            String generation=libraries.currentId();if(generation==null)throw new DetectorClient.DetectorFailure("LIBRARY_UNAVAILABLE");
            var library=db.queryForMap("SELECT manifest_sha256 FROM library_generation WHERE id=?",generation);String libraryHash=library.get("manifest_sha256").toString();
            String org=db.queryForObject("SELECT organization_id FROM manuscript WHERE id=?",String.class,batch.get("manuscript_id"));ObjectNode pin;
            try{pin=releases.textSelection(org,main.path("configs").path("textConfig"),generation,libraryHash);}
            catch(ApiException error){
                if(!"REFERENCE_PROFILE_STALE".equals(error.code))throw error;
                // Record a rejected selection, without pinning a model that never ran.
                var rejected=json.createObjectNode().put("selectionStatus","REJECTED").put("libraryGenerationId",generation).put("libraryManifestSha256",libraryHash);
                for(String item:db.queryForList("SELECT id FROM detection_item WHERE batch_id=? AND status='QUEUED'",String.class,batchId)){
                    if(onlyItem!=null&&!onlyItem.equals(item))continue;
                    String attempt=attempts.start(item,rejected);attempts.failIfCurrent(attempt,error.code,error.getMessage());
                }
                detection.finish(batchId);throw error;
            }
            pin.set("imageConfig",main.path("configs").path("imageConfig"));pin.set("ocrConfig",client.frozenOcrConfig());pin.put("libraryGenerationId",generation).put("libraryManifestSha256",libraryHash);
            pipeline=detection.pin(batchId,generation,pin);
        }else pipeline=JsonSupport.parse(json,batch.get("pipeline_manifest_json").toString());
        client.ensureTextAdapter(pipeline);
        db.update("UPDATE detection_batch SET status='RUNNING',started_at=COALESCE(started_at,UTC_TIMESTAMP(3)) WHERE id=?",batchId);
        var items=db.queryForList("SELECT * FROM detection_item WHERE batch_id=? AND status='QUEUED' ORDER BY CASE type WHEN 'TEXT' THEN 0 WHEN 'IMAGE' THEN 1 ELSE 2 END,id",batchId);
        for(var item:items){
            String itemId=item.get("id").toString();if(onlyItem!=null && !onlyItem.equals(itemId))continue;
            String type=item.get("type").toString();String attempt=attempts.start(itemId,pipeline);
            try(var budget=client.budget("TEXT".equals(type)?"text":"IMAGE".equals(type)?"image":"ocrAndText")){
                ObjectNode request=json.createObjectNode();request.put("taskId",itemId).put("attemptId",attempt).put("scene",batch.get("scene").toString()).put("versionId",batch.get("submission_version_id").toString()).put("inputSnapshotKey",batch.get("input_snapshot_key").toString()).put("inputSha256",batch.get("input_sha256").toString()).put("libraryGenerationId",pipeline.path("libraryGenerationId").asText()).put("libraryManifestSha256",pipeline.path("libraryManifestSha256").asText()).put("excludeManuscriptId",batch.get("manuscript_id").toString());
                JsonNode result;
                if("TEXT".equals(type)){
                    request.put("text",batch.get("plain_text").toString()).put("configId",pipeline.path("textConfig").path("configId").asText());result=client.call(false,"/detect/text",request,"text");
                }else{
                    var file=references.fileForVersion(batch.get("submission_version_id").toString(),item.get("image_node_id").toString());
                    request.put("fileId",file.path("fileId").asText()).put("path",file.path("path").asText()).put("fileSha256",file.path("fileSha256").asText());
                    if("IMAGE".equals(type)){
                        request.put("configId",pipeline.path("imageConfig").path("configId").asText());result=client.call(false,"/detect/image",request,"image");
                    }else{
                        var recognized=references.recognize(request,pipeline.path("ocrConfig"),ocr);
                        var combined=(ObjectNode)recognized.deepCopy();
                        if(!recognized.path("combinedText").asText().isBlank()){
                            combined.put("textSearchStatus","RUNNING");attempts.checkpointIfCurrent(attempt,combined);
                            request.put("text",recognized.path("combinedText").asText()).put("configId",pipeline.path("textConfig").path("configId").asText());
                            var text=client.call(false,"/detect/text",request,"ocrAndText");combined.set("textEvidence",text.path("evidence"));combined.put("textSearchStatus","COMPLETED");
                        }
                        combined.put("imageNodeId",item.get("image_node_id").toString());result=combined;
                    }
                }
                attempts.completeIfCurrent(attempt,result);
            }catch(Exception error){String code=error instanceof DetectorClient.DetectorFailure failure?failure.code:"DETECTION_FAILED";attempts.failIfCurrent(attempt,code,"该项处理失败，其他项目继续执行");
                if(Set.of("DETECTOR_TIMEOUT","PROCESS_BUSY").contains(code)){detection.finish(batchId);throw new WaitingService();}
            }
        }
        detection.finish(batchId);
    }
}
