package local.campus.review.content;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.annotation.PreDestroy;
import local.campus.review.common.*;
import local.campus.review.detection.DetectorClient;
import local.campus.review.reference.LibraryGenerationService;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class InspectionWorker {
    private final InspectionService checks;private final DetectorClient detector;private final LibraryGenerationService libraries;
    private final ExecutorService executor=Executors.newSingleThreadExecutor(r->{var t=new Thread(r,"manuscript-checks");t.setDaemon(true);return t;});
    private final ScheduledExecutorService monitor=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"check-monitor");t.setDaemon(true);return t;});
    private final AtomicBoolean busy=new AtomicBoolean();private volatile boolean ready;
    private final local.campus.review.workbench.ReleaseService releases;
    public InspectionWorker(InspectionService checks,DetectorClient detector,LibraryGenerationService libraries,local.campus.review.workbench.ReleaseService releases){this.checks=checks;this.detector=detector;this.libraries=libraries;this.releases=releases;}
    @EventListener(ApplicationReadyEvent.class) public void ready(){checks.db.update("UPDATE document_check SET status='INTERRUPTED',error_message='检查已中断，请重新检查',finished_at=UTC_TIMESTAMP(3) WHERE status='RUNNING'");ready=true;}
    @Scheduled(fixedDelay=750) public void poll(){if(!ready || !busy.compareAndSet(false,true))return;executor.submit(()->{try{runOne();}catch(Exception e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("Document checks unavailable ({})",e.getClass().getSimpleName());}finally{busy.set(false);}});}
    private void runOne()throws Exception{
        var jobs=checks.db.queryForList("SELECT * FROM document_check WHERE status='QUEUED' OR (status IN ('WAITING_SERVICE','WAITING_RESOURCE') AND retry_after<=UTC_TIMESTAMP(3)) ORDER BY created_at LIMIT 1");if(jobs.isEmpty())return;
        var job=jobs.getFirst();String id=job.get("id").toString();
        if(checks.db.update("UPDATE document_check SET status='RUNNING',started_at=COALESCE(started_at,UTC_TIMESTAMP(3)),error_message=NULL WHERE id=? AND status IN ('QUEUED','WAITING_SERVICE','WAITING_RESOURCE')",id)!=1)return;
        checks.event(id,Map.of("stage","RUNNING"));var payload=(ObjectNode)JsonSupport.parse(checks.json,job.get("payload_json").toString());
        try{
            JsonNode result;
            if("CONTENT".equals(job.get("kind"))){result=content(id,payload);if(result==null)return;}
            else {result=python(id,payload);if(result==null)return;}
            if(!payload.path("inputHash").asText().equals(result.path("inputHash").asText()))throw new IOException("检查结果与稿件版本不一致");
            if(payload.has("modelProfile")&&!payload.path("modelProfile").equals(result.path("modelProfile")))throw new IOException("检查模型与选定方案不一致");
            if(checks.db.update("UPDATE document_check SET status='COMPLETED',result_json=?,finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status='RUNNING'",result.toString(),id)==1)checks.event(id,Map.of("stage","COMPLETED"));
        }catch(Exception error){
            if(error instanceof DetectorClient.DetectorFailure failure && "PROCESS_BUSY".equals(failure.code)){
                if(checks.db.update("UPDATE document_check SET status='WAITING_RESOURCE',error_message='等待模型计算资源',retry_after=DATE_ADD(UTC_TIMESTAMP(3),INTERVAL 30 SECOND) WHERE id=? AND status='RUNNING'",id)==1)
                    checks.event(id,Map.of("stage","WAITING_RESOURCE"));
                return;
            }
            String message=Objects.toString(error.getMessage(),"检查未完成");if(message.length()>900)message=message.substring(0,900);if(checks.db.update("UPDATE document_check SET status='FAILED',error_message=?,finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status='RUNNING'",message,id)==1)checks.event(id,Map.of("stage","FAILED","message",message));
        }
    }
    private JsonNode python(String id,ObjectNode payload)throws Exception{
        var folder=checks.settings.runtime().resolve("document-checks").resolve(id);Files.createDirectories(folder);var file=folder.resolve("input.json");Files.writeString(file,payload.toString());
        var builder=new ProcessBuilder(checks.settings.root().resolve("runtime/environments/final-training/Scripts/python.exe").toString(),"-B",checks.settings.root().resolve("app/scripts/check_manuscript.py").toString(),file.toString()).directory(checks.settings.root().toFile()).redirectError(folder.resolve("stderr.log").toFile());
        builder.environment().putAll(Map.of("HF_HUB_OFFLINE","1","TOKENIZERS_PARALLELISM","false","OMP_NUM_THREADS","2","MKL_NUM_THREADS","2","PYTHONIOENCODING","utf-8"));
        if(!Set.of("GRAMMAR_MODEL","IMAGE_TEXT").contains(payload.path("kind").asText()))builder.environment().put("CUDA_VISIBLE_DEVICES","-1");
        var process=builder.start();checks.processes.put(id,process);var timeout=monitor.schedule(()->InspectionService.stop(process),30,TimeUnit.MINUTES);
        var cancellation=monitor.scheduleWithFixedDelay(()->{try{if(!"RUNNING".equals(checks.db.queryForObject("SELECT status FROM document_check WHERE id=?",String.class,id)))InspectionService.stop(process);}catch(Exception e){InspectionService.stop(process);}},2,2,TimeUnit.SECONDS);
        JsonNode result=null;String message="检查进程未返回结果";
        try(var reader=new BufferedReader(new InputStreamReader(process.getInputStream(),StandardCharsets.UTF_8))){String line;while((line=reader.readLine())!=null){var record=checks.json.readTree(line);switch(record.path("type").asText()){case "event" -> checks.event(id,record.path("data"));case "result" -> result=record.path("data");case "error" -> message=record.path("data").path("message").asText();default -> throw new IOException("检查返回格式无效");}}int code=process.waitFor();if(code==75){if(checks.db.update("UPDATE document_check SET status='WAITING_RESOURCE',error_message=?,retry_after=DATE_ADD(UTC_TIMESTAMP(3),INTERVAL 30 SECOND) WHERE id=? AND status='RUNNING'",message,id)==1)checks.event(id,Map.of("stage","WAITING_RESOURCE"));return null;}if(code!=0 || result==null)throw new IOException(message);return result;}
        finally{timeout.cancel(false);cancellation.cancel(false);checks.processes.remove(id,process);if(process.isAlive())InspectionService.stop(process);}
    }
    private JsonNode content(String id,ObjectNode payload){
        var health=detector.health(false);
        if(!health.path("ready").asBoolean() || health.path("busy").asBoolean()){checks.db.update("UPDATE document_check SET status='WAITING_SERVICE',error_message='等待内容检测服务',retry_after=DATE_ADD(UTC_TIMESTAMP(3),INTERVAL 30 SECOND) WHERE id=? AND status='RUNNING'",id);checks.event(id,Map.of("stage","WAITING_SERVICE"));return null;}
        if(!payload.hasNonNull("contentProfile")){
            var captured=checks.contentProfiles.capture(payload.path("manuscriptId").asText(),false);
            if(captured==null)throw new DetectorClient.DetectorFailure("LIBRARY_UNAVAILABLE");
            payload.set("contentProfile",captured);checks.db.update("UPDATE document_check SET payload_json=? WHERE id=? AND status='RUNNING'",payload.toString(),id);
        }
        var selected=payload.path("contentProfile");String generation=selected.path("libraryGenerationId").asText(),libraryHash=selected.path("libraryManifestSha256").asText();
        var manifest=libraries.lockedManifest(generation);if(!libraryHash.equals(checks.db.queryForObject("SELECT manifest_sha256 FROM library_generation WHERE id=?",String.class,generation)))throw new DetectorClient.DetectorFailure("LIBRARY_HASH_MISMATCH");
        detector.ensureTextAdapter(selected);
        var request=checks.json.createObjectNode().put("taskId",id).put("attemptId",id).put("scene","PRECHECK").put("versionId",id).put("inputSnapshotKey","check:"+id).put("inputSha256",payload.path("inputHash").asText()).put("libraryGenerationId",generation).put("libraryManifestSha256",libraryHash).put("excludeManuscriptId",payload.path("manuscriptId").asText()).put("text",payload.path("plainText").asText());
        request.put("configId",selected.path("textConfig").path("configId").asText());var output=(ObjectNode)detector.call(false,"/detect/text",request,"text");output.put("inputHash",payload.path("inputHash").asText());output.set("contentProfile",selected);if(selected.has("releaseId"))output.set("releaseId",selected.get("releaseId"));
        var document=checks.json.convertValue(payload.path("document"),DocumentModels.DocumentInput.class);var extracted=checks.codec.validateAndExtract(document);checks.citations.annotate(output.path("evidence"),extracted);for(var member:output.path("bundleResults"))checks.citations.annotate(member.path("result").path("evidence"),extracted);
        var images=output.putArray("imageResults");for(var image:payload.path("images")){var input=request.deepCopy();input.remove("text");input.put("fileId",image.path("fileId").asText()).put("fileSha256",image.path("sha256").asText()).put("path",image.path("path").asText()).put("configId",selected.path("imageConfig").path("configId").asText());var result=(ObjectNode)detector.call(false,"/detect/image",input,"image");result.put("nodeId",image.path("nodeId").asText());images.add(result);}
        return output;
    }
    @PreDestroy public void close(){ready=false;checks.processes.values().forEach(InspectionService::stop);executor.shutdownNow();monitor.shutdownNow();}
}
