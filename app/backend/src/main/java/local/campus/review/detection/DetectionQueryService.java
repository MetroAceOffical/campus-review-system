package local.campus.review.detection;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.content.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.util.*;

@Service
public class DetectionQueryService {
    private final JdbcTemplate db;private final ObjectMapper json;
    private final CitationService citations;private final DocumentCodec codec;
    public DetectionQueryService(JdbcTemplate db,ObjectMapper json,CitationService citations,DocumentCodec codec){this.db=db;this.json=json;this.citations=citations;this.codec=codec;}
    private Map<String,Object> require(CurrentUser user,String id,boolean report){
        if(report)AccessPolicy.requireReviewer(user);
        var rows=db.queryForList("SELECT b.*,v.version_no,v.manuscript_id,m.organization_id FROM detection_batch b JOIN submission_version v ON v.id=b.submission_version_id JOIN manuscript m ON m.id=v.manuscript_id WHERE b.id=?",id);
        if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到检测批次");var row=rows.getFirst();
        if(user.role()!=CurrentUser.Role.REVIEWER)AccessPolicy.requireOrganization(user,row.get("organization_id").toString());return row;
    }
    public JsonNode progress(CurrentUser user,String id){require(user,id,false);return snapshot(id);}
    public JsonNode snapshot(String id){
        var batch=db.queryForMap("SELECT * FROM detection_batch WHERE id=?",id);
        var result=json.createObjectNode().put("batchId",id).put("status",batch.get("status").toString());var items=result.putArray("items");int completed=0;
        for(String field:new String[]{"created_at","started_at","finished_at"}){String key=switch(field){case "created_at"->"createdAt";case "started_at"->"startedAt";default->"finishedAt";};if(batch.get(field)==null)result.putNull(key);else result.put(key,((java.time.LocalDateTime)batch.get(field)).atOffset(java.time.ZoneOffset.UTC).toString());}
        for(var item:db.queryForList("SELECT * FROM detection_item WHERE batch_id=? ORDER BY id",id)){
            var value=items.addObject().put("itemId",item.get("id").toString()).put("type",item.get("type").toString()).put("targetKey",item.get("target_key").toString()).put("status",item.get("status").toString());
            if(item.get("active_attempt_id")==null)value.putNull("activeAttemptId");else value.put("activeAttemptId",item.get("active_attempt_id").toString());
            if(!Set.of("QUEUED","RUNNING").contains(item.get("status")))completed++;
        }
        result.put("completedItems",completed).put("totalItems",items.size());return result;
    }
    public JsonNode report(CurrentUser user,String id){
        var batch=require(user,id,true);var result=(com.fasterxml.jackson.databind.node.ObjectNode)snapshot(id);
        result.put("reportSchemaVersion","1").put("scene",batch.get("scene").toString()).put("inputSnapshotKey",batch.get("input_snapshot_key").toString()).put("inputSha256",batch.get("input_sha256").toString()).put("submissionId",batch.get("submission_version_id").toString()).put("versionNo",((Number)batch.get("version_no")).intValue());
        result.put("generatedAt",java.time.OffsetDateTime.now(java.time.ZoneOffset.UTC).toString());
        if(batch.get("library_generation_id")==null)result.putNull("libraryGenerationId");else result.put("libraryGenerationId",batch.get("library_generation_id").toString());
        result.set("pipelineManifest",batch.get("pipeline_manifest_json")==null?json.nullNode():JsonSupport.parse(json,batch.get("pipeline_manifest_json").toString()));
        var version=db.queryForMap("SELECT * FROM submission_version WHERE id=?",batch.get("submission_version_id"));
        var document=codec.validateAndExtract(new DocumentModels.DocumentInput(version.get("title").toString(),version.get("schema_version").toString(),JsonSupport.parse(json,version.get("content_json").toString()),json.convertValue(JsonSupport.parse(json,version.get("sources_json").toString()),new com.fasterxml.jackson.core.type.TypeReference<java.util.List<DocumentModels.Source>>(){})));
        for(var item:result.path("items")){
            var value=(com.fasterxml.jackson.databind.node.ObjectNode)item;
            if(item.path("activeAttemptId").isNull()){value.putNull("activeAttempt");value.set("evidence",json.createArrayNode());continue;}
            var attempt=db.queryForMap("SELECT * FROM detection_attempt WHERE id=?",item.path("activeAttemptId").asText());
            var execution=json.createObjectNode().put("attemptId",attempt.get("id").toString()).put("attemptNo",((Number)attempt.get("attempt_no")).intValue()).put("status",attempt.get("status").toString());
            execution.put("startedAt",((java.time.LocalDateTime)attempt.get("started_at")).atOffset(java.time.ZoneOffset.UTC).toString());if(attempt.get("finished_at")==null)execution.putNull("finishedAt");else execution.put("finishedAt",((java.time.LocalDateTime)attempt.get("finished_at")).atOffset(java.time.ZoneOffset.UTC).toString());
            execution.set("modelConfig",JsonSupport.parse(json,attempt.get("model_config_json").toString()));execution.put("errorCode",Objects.toString(attempt.get("error_code"),"")).put("errorMessage",Objects.toString(attempt.get("error_message"),""));
            var output=JsonSupport.parse(json,attempt.get("result_json").toString());execution.set("result",output);value.set("activeAttempt",execution);
            value.set("evidence",output.path("evidence").isArray()?output.path("evidence"):output.path("textEvidence").isArray()?output.path("textEvidence"):json.createArrayNode());value.set("qualityFlags",output.path("qualityFlags").isArray()?output.path("qualityFlags"):json.createArrayNode());
            if("TEXT".equals(item.path("type").asText())){citations.annotate(value.path("evidence"),document);for(var member:output.path("bundleResults"))citations.annotate(member.path("result").path("evidence"),document);}
        }
        return result;
    }
}
