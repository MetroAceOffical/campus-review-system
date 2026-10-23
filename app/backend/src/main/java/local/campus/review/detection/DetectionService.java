package local.campus.review.detection;

import com.fasterxml.jackson.databind.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;

@Service
public class DetectionService {
    private final JdbcTemplate db;private final ObjectMapper json;
    public DetectionService(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
    @Transactional public String createFormalBatch(String versionId,String inputHash){
        var version=db.queryForMap("SELECT * FROM submission_version WHERE id=? FOR UPDATE",versionId);
        if(!inputHash.equals(version.get("content_sha256")))throw new ApiException(409,"INPUT_MISMATCH","检测输入与送审快照不一致");
        var existing=db.queryForList("SELECT id FROM detection_batch WHERE submission_version_id=? ORDER BY batch_no LIMIT 1",versionId);
        if(!existing.isEmpty())return existing.getFirst().get("id").toString();
        long batch=SqlSupport.insert(db,"INSERT INTO detection_batch(submission_version_id,scene,input_snapshot_key,input_sha256,batch_no,status,created_at) VALUES(?,'FORMAL',?,?,1,'QUEUED',UTC_TIMESTAMP(3))",versionId,"submission:"+versionId,inputHash);
        item(batch,"TEXT","BODY",null);
        walk(JsonSupport.parse(json,version.get("content_json").toString()),batch);
        db.update("INSERT INTO background_job(kind,batch_id,status,payload_json,created_at) VALUES('DETECT_BATCH',?,'QUEUED','{}',UTC_TIMESTAMP(3))",batch);
        return Long.toString(batch);
    }
    private void walk(JsonNode node,long batch){
        if("campusImage".equals(node.path("type").asText())){String id=node.path("attrs").path("nodeId").asText();item(batch,"IMAGE",id,id);item(batch,"OCR_AND_TEXT",id,id);}
        for(var child:node.path("content"))walk(child,batch);
    }
    private void item(long batch,String type,String key,String node){db.update("INSERT INTO detection_item(batch_id,type,target_key,image_node_id,status,updated_at) VALUES(?,?,?,?,'QUEUED',UTC_TIMESTAMP(3))",batch,type,key,node);}
    @Transactional public JsonNode pin(String batchId,String generationId,JsonNode pipeline){
        var row=db.queryForMap("SELECT * FROM detection_batch WHERE id=? FOR UPDATE",batchId);
        if(row.get("pipeline_manifest_json")!=null)return JsonSupport.parse(json,row.get("pipeline_manifest_json").toString());
        if(row.get("cancelled_at")!=null)throw new ApiException(409,"BATCH_CANCELLED","检测批次已取消");
        db.update("UPDATE detection_batch SET library_generation_id=?,pipeline_manifest_json=?,status='RUNNING',started_at=UTC_TIMESTAMP(3) WHERE id=?",generationId,JsonSupport.encode(json,pipeline),batchId);
        return pipeline;
    }
    public void finish(String batch){
        var statuses=db.queryForList("SELECT status FROM detection_item WHERE batch_id=?",String.class,batch);
        String status=statuses.stream().anyMatch(s->Set.of("QUEUED","RUNNING").contains(s))?"RUNNING":statuses.stream().anyMatch(s->Set.of("FAILED","INTERRUPTED").contains(s))?"PARTIAL_FAILED":statuses.stream().allMatch(s->"CANCELLED".equals(s))?"CANCELLED":"COMPLETED";
        db.update("UPDATE detection_batch SET status=?,finished_at=IF(?='RUNNING',NULL,UTC_TIMESTAMP(3)) WHERE id=?",status,status,batch);
    }
}
