package local.campus.review.reference;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.common.*;
import local.campus.review.detection.DetectorClient;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

@Service
public class ReferenceProcessor {
    private final JdbcTemplate db;private final ObjectMapper json;private final RuntimeSettings settings;
    private final DetectorClient client;private final LibraryGenerationService libraries;
    public ReferenceProcessor(JdbcTemplate db,ObjectMapper json,RuntimeSettings settings,DetectorClient client,LibraryGenerationService libraries){this.db=db;this.json=json;this.settings=settings;this.client=client;this.libraries=libraries;}
    public ObjectNode fileForVersion(String version,String node){return file(db.queryForMap("SELECT f.* FROM stored_file f JOIN file_binding b ON b.file_id=f.id WHERE b.submission_version_id=? AND b.node_id=? AND b.purpose='BODY_IMAGE'",version,node));}
    private ObjectNode file(Map<String,Object> row){
        var path=settings.runtime().resolve("uploads").resolve(row.get("storage_key").toString()).normalize();
        if(!path.startsWith(settings.runtime().resolve("uploads")))throw new DetectorClient.DetectorFailure("FILE_OUTSIDE_ROOT");
        return json.createObjectNode().put("fileId",row.get("id").toString()).put("path",path.toString()).put("fileSha256",row.get("sha256").toString());
    }
    private String sha(Path file)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));}
    private void write(Path target,JsonNode value)throws Exception{
        Files.createDirectories(target.getParent());Path temporary=target.resolveSibling(target.getFileName()+".tmp");Files.writeString(temporary,JsonSupport.encode(json,value));Files.move(temporary,target,StandardCopyOption.REPLACE_EXISTING);
    }
    public JsonNode recognize(ObjectNode input,JsonNode config,JsonNode health){
        if(!config.hasNonNull("configId"))throw new DetectorClient.DetectorFailure("CONFIG_UNAVAILABLE");
        String key=JsonSupport.hash(json,Map.of("fileSha256",input.path("fileSha256").asText(),"config",config));
        Path cache=settings.runtime().resolve("derived/ocr").resolve(key+".json");
        try{
            if(Files.isRegularFile(cache)){
                var saved=json.readTree(Files.readString(cache));
                if(saved.path("actualConfig").equals(config) && saved.path("fileSha256").equals(input.path("fileSha256")) && saved.path("recognitionLines").isArray() && saved.path("combinedText").isTextual()){
                    var result=(ObjectNode)saved.deepCopy();for(String field:new String[]{"taskId","attemptId","fileId"})result.set(field,input.path(field));result.put("recognitionCacheHit",true);return result;
                }
            }
        }catch(Exception ignored){/* A damaged cache is rebuilt; it is never a successful OCR result. */}
        if(!health.path("ready").asBoolean())throw new DetectorClient.DetectorFailure("OCR_SERVICE_UNAVAILABLE");
        if(!config.path("configId").equals(health.path("config").path("configId")))throw new DetectorClient.DetectorFailure("CONFIG_UNAVAILABLE");
        var request=input.deepCopy();request.put("configId",config.path("configId").asText());
        var result=client.call(true,"/recognize",request,"ocrAndText");
        if(!result.path("actualConfig").equals(config))throw new DetectorClient.DetectorFailure("RESULT_CONFIG_MISMATCH");
        try{write(cache,result);}catch(Exception e){throw new DetectorClient.DetectorFailure("OCR_CACHE_WRITE_FAILED");}
        return result;
    }
    public void prepare(String revision,JsonNode ocr,Set<String> requested){
        var row=db.queryForMap("SELECT * FROM reference_revision WHERE id=?",revision);
        var artifacts=(ObjectNode)JsonSupport.parse(json,row.get("artifacts_json").toString());var parts=artifacts.withObject("parts");
        parts.set("BODY",json.createObjectNode().put("status",artifacts.path("plainText").asText().isBlank()?"NOT_APPLICABLE":"AVAILABLE"));
        db.update("UPDATE reference_revision SET processing_status='PROCESSING',artifacts_json=? WHERE id=?",JsonSupport.encode(json,artifacts),revision);
        var images=db.queryForList("SELECT f.*,b.node_id FROM file_binding b JOIN stored_file f ON f.id=b.file_id WHERE b.reference_revision_id=? AND b.purpose='BODY_IMAGE' ORDER BY b.id",revision);
        for(var image:images){
            String node=image.get("node_id").toString();
            var request=file(image);request.put("taskId","reference:"+revision+":"+node).put("attemptId",UUID.randomUUID().toString());
            if(requested.isEmpty() || requested.contains("OCR:"+node)){
                try{
                    var result=recognize(request,client.frozenOcrConfig(),ocr);
                    parts.set("OCR:"+node,json.createObjectNode().put("status","AVAILABLE").set("result",result));
                }catch(Exception error){parts.set("OCR:"+node,json.createObjectNode().put("status","FAILED").put("errorCode",error instanceof DetectorClient.DetectorFailure failure?failure.code:"OCR_FAILED"));}
            }
            if(requested.isEmpty() || requested.contains("IMAGE:"+node))parts.set("IMAGE:"+node,json.createObjectNode().put("status","PENDING_INDEX"));
            db.update("UPDATE reference_revision SET artifacts_json=? WHERE id=?",JsonSupport.encode(json,artifacts),revision);
        }
        db.update("UPDATE reference_revision SET processing_status='PREPARED',artifacts_json=? WHERE id=?",JsonSupport.encode(json,artifacts),revision);
        if(db.queryForObject("SELECT COUNT(*) FROM background_job WHERE kind='REFRESH_LIBRARY' AND status IN ('QUEUED','WAITING_SERVICE')",Integer.class)==0)
            db.update("INSERT INTO background_job(kind,status,payload_json,created_at) VALUES('REFRESH_LIBRARY','QUEUED','{}',UTC_TIMESTAMP(3))");
    }
    public void refresh(){
        String expected=libraries.currentId();String generation=libraries.reserve();
        try{
            var manifest=json.createObjectNode().put("generationId",generation);var documents=manifest.putArray("documents");var pictures=manifest.putArray("images");
            var revisions=db.queryForList("SELECT r.*,w.manuscript_id FROM reference_work w JOIN reference_revision r ON r.reference_work_id=w.id WHERE w.enabled=true AND r.processing_status IN ('PREPARED','READY','PARTIAL') AND r.revision_no=(SELECT MAX(x.revision_no) FROM reference_revision x WHERE x.reference_work_id=w.id AND x.processing_status IN ('PREPARED','READY','PARTIAL')) ORDER BY w.id");
            for(var revision:revisions){
                String id=revision.get("id").toString();var artifacts=JsonSupport.parse(json,revision.get("artifacts_json").toString());var metadata=JsonSupport.parse(json,revision.get("source_metadata_json").toString());
                var base=json.createObjectNode().put("sourceWorkId",revision.get("reference_work_id").toString()).put("sourceRevisionId",id).put("title",revision.get("title").toString());
                if(revision.get("manuscript_id")==null)base.putNull("manuscriptId");else base.put("manuscriptId",revision.get("manuscript_id").toString());
                base.set("sourceMetadata",metadata);if(metadata.hasNonNull("url"))base.set("url",metadata.get("url"));
                if(!artifacts.path("plainText").asText().isBlank())documents.add(base.deepCopy().put("sourceKey",id+":BODY").put("sourceKind","BODY").put("text",artifacts.path("plainText").asText()));
                var images=db.queryForList("SELECT f.*,b.node_id FROM stored_file f JOIN file_binding b ON b.file_id=f.id WHERE b.reference_revision_id=? AND b.purpose='BODY_IMAGE' ORDER BY b.id",id);
                for(var image:images){
                    String node=image.get("node_id").toString();var entry=base.deepCopy();entry.setAll(file(image));entry.put("nodeId",node);pictures.add(entry);
                    var recognized=artifacts.path("parts").path("OCR:"+node).path("result");
                    if(!recognized.path("combinedText").asText().isBlank()){
                        var text=base.deepCopy().put("sourceKey",id+":OCR:"+node).put("sourceKind","IMAGE_OCR").put("text",recognized.path("combinedText").asText());
                        var sourceMetadata=(ObjectNode)metadata.deepCopy();sourceMetadata.put("sourceFileId",image.get("id").toString()).put("imageNodeId",node);sourceMetadata.set("ocr",recognized);text.set("sourceMetadata",sourceMetadata);documents.add(text);
                    }
                }
            }
            Path input=settings.runtime().resolve("indexes").resolve(generation).resolve("input-manifest.json");write(input,manifest);
            var response=client.call(false,"/library/build",json.createObjectNode().put("manifestPath",input.toString()).put("manifestSha256",sha(input)),"library");
            if(!generation.equals(response.path("generationId").asText()))throw new DetectorClient.DetectorFailure("RESULT_IDENTITY_MISMATCH");
            for(var part:response.path("partResults")){
                String revision=part.path("sourceRevisionId").asText();if(!part.path("key").asText().startsWith("IMAGE:"))continue;
                var artifacts=(ObjectNode)JsonSupport.parse(json,db.queryForObject("SELECT artifacts_json FROM reference_revision WHERE id=?",String.class,revision));
                artifacts.withObject("parts").set(part.path("key").asText(),part);db.update("UPDATE reference_revision SET artifacts_json=? WHERE id=?",JsonSupport.encode(json,artifacts),revision);
            }
            libraries.markReady(generation,response.path("manifestSha256").asText());libraries.activate(generation,expected);
            var usable=new HashSet<String>();libraries.currentManifest().path("enabledReferenceWorkIds").forEach(id->usable.add(id.asText()));
            for(var revision:revisions){
                var artifacts=JsonSupport.parse(json,db.queryForObject("SELECT artifacts_json FROM reference_revision WHERE id=?",String.class,revision.get("id")));
                boolean failed=false;for(var part:artifacts.path("parts"))if("FAILED".equals(part.path("status").asText()))failed=true;
                String status=!usable.contains(revision.get("reference_work_id").toString())?"FAILED":failed?"PARTIAL":"READY";
                db.update("UPDATE reference_revision SET processing_status=? WHERE id=?",status,revision.get("id"));
            }
        }catch(Exception error){libraries.fail(generation,error instanceof DetectorClient.DetectorFailure failure?failure.code:"LIBRARY_BUILD_FAILED");throw error instanceof RuntimeException runtime?runtime:new IllegalStateException(error);}
    }
}
