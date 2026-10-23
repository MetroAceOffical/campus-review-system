package local.campus.review.reference;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.content.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;
import static local.campus.review.content.DocumentModels.*;

@Service
public class ReferenceService {
    public record ReferenceInput(String title,String schemaVersion,JsonNode content,List<Source> sources,JsonNode sourceMetadata){}
    private final JdbcTemplate db;private final ObjectMapper json;private final DocumentCodec codec;private final FileService files;
    private final IdempotencyStore keys;private final LibraryGenerationService libraries;
    public ReferenceService(JdbcTemplate db,ObjectMapper json,DocumentCodec codec,FileService files,IdempotencyStore keys,LibraryGenerationService libraries){this.db=db;this.json=json;this.codec=codec;this.files=files;this.keys=keys;this.libraries=libraries;}
    @Transactional public JsonNode create(CurrentUser user,String key,ReferenceInput input){
        AccessPolicy.requireAdmin(user);
        var cached=keys.begin(user.userId(),"REFERENCE_CREATE",key,JsonSupport.hash(json,input));if(cached!=null)return cached;
        var result=codec.validateForSubmission(new DocumentInput(input.title(),input.schemaVersion(),input.content(),input.sources()));
        if(input.sourceMetadata()==null || !input.sourceMetadata().isObject())throw new ApiException(400,"VALIDATION_ERROR","请填写参考材料来源");
        var metadata=(com.fasterxml.jackson.databind.node.ObjectNode)input.sourceMetadata().deepCopy();String type=metadata.path("sourceType").asText();
        if("URL".equals(type))DocumentCodec.checkUrl(metadata.path("url").asText(),false);
        else if(!"MANUAL".equals(type) || metadata.path("description").asText().isBlank() || metadata.path("description").asText().length()>2000)throw new ApiException(400,"VALIDATION_ERROR","请填写有效的来源类型和说明");
        metadata.set("bodySources",json.valueToTree(result.document().sources()));
        LocalDateTime originalPublishedAt=null;
        if(metadata.hasNonNull("published_at")) {
            try {originalPublishedAt=OffsetDateTime.parse(metadata.path("published_at").asText()).withOffsetSameInstant(ZoneOffset.UTC).toLocalDateTime();}
            catch(java.time.format.DateTimeParseException error){throw new ApiException(400,"VALIDATION_ERROR","原发布时间须包含明确时区");}
        }
        for(var image:result.images())files.requireBindable(user,image.fileId());
        long work=SqlSupport.insert(db,"INSERT INTO reference_work(manuscript_id,origin_type,enabled,created_by,created_at) VALUES(NULL,'MANUAL',true,?,UTC_TIMESTAMP(3))",user.userId());
        var artifacts=json.createObjectNode();artifacts.put("plainText",result.plainText());artifacts.put("contentSha256",result.contentHash());artifacts.set("parts",json.createObjectNode());
        long revision=SqlSupport.insert(db,"INSERT INTO reference_revision(reference_work_id,revision_no,title,content_json,source_metadata_json,original_published_at,processing_status,artifacts_json,created_at) VALUES(?,1,?,?,?,?,'QUEUED',?,UTC_TIMESTAMP(3))",work,input.title(),JsonSupport.encode(json,result.document().content()),JsonSupport.encode(json,metadata),originalPublishedAt,JsonSupport.encode(json,artifacts));
        for(var image:result.images())db.update("INSERT INTO file_binding(file_id,reference_revision_id,node_id,purpose) VALUES(?,?,?,'BODY_IMAGE')",image.fileId(),revision,image.nodeId());
        long job=SqlSupport.insert(db,"INSERT INTO background_job(kind,reference_revision_id,status,payload_json,created_at) VALUES('PREPARE_REFERENCE',?,'QUEUED','{}',UTC_TIMESTAMP(3))",revision);
        var receipt=json.valueToTree(Map.of("referenceId",Long.toString(work),"revisionId",Long.toString(revision),"jobId",Long.toString(job),"processingStatus","QUEUED"));
        keys.complete(user.userId(),"REFERENCE_CREATE",key,receipt);return receipt;
    }
    public JsonNode list(CurrentUser user,int page,int pageSize){
        AccessPolicy.requireAdmin(user);if(page<1 || pageSize<1 || pageSize>100)throw new ApiException(400,"VALIDATION_ERROR","分页参数无效");
        var effective=new HashSet<String>();libraries.currentManifest().path("enabledReferenceWorkIds").forEach(id->effective.add(id.asText()));
        var rows=db.queryForList("SELECT w.id,w.enabled,w.origin_type,w.created_at,r.id AS revision_id,r.title,r.processing_status,r.source_metadata_json,r.artifacts_json FROM reference_work w JOIN reference_revision r ON r.reference_work_id=w.id AND r.revision_no=(SELECT MAX(x.revision_no) FROM reference_revision x WHERE x.reference_work_id=w.id) ORDER BY w.id DESC LIMIT ? OFFSET ?",pageSize,(long)(page-1)*pageSize);
        var items=new ArrayList<Map<String,Object>>();
        for(var row:rows){var item=new LinkedHashMap<String,Object>();String id=row.get("id").toString();item.put("referenceId",id);item.put("revisionId",row.get("revision_id").toString());item.put("title",row.get("title"));item.put("originType",row.get("origin_type"));item.put("requestedEnabled",row.get("enabled"));item.put("effectiveEnabled",effective.contains(id));item.put("processingStatus",row.get("processing_status"));item.put("sourceMetadata",JsonSupport.parse(json,row.get("source_metadata_json").toString()));item.put("parts",JsonSupport.parse(json,row.get("artifacts_json").toString()).path("parts"));item.put("createdAt",((LocalDateTime)row.get("created_at")).atOffset(ZoneOffset.UTC).toString());items.add(item);}
        return json.valueToTree(Map.of("items",items,"page",page,"pageSize",pageSize,"total",db.queryForObject("SELECT COUNT(*) FROM reference_work",Long.class)));
    }
    @Transactional public JsonNode setEnabled(CurrentUser user,String id,String key,boolean enabled){
        AccessPolicy.requireAdmin(user);var cached=keys.begin(user.userId(),"REFERENCE_ENABLED",key,JsonSupport.hash(json,Map.of("id",id,"enabled",enabled)));if(cached!=null)return cached;
        var rows=db.queryForList("SELECT * FROM reference_work WHERE id=? FOR UPDATE",id);if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到参考作品");
        db.update("UPDATE reference_work SET enabled=? WHERE id=?",enabled,id);
        long job=SqlSupport.insert(db,"INSERT INTO background_job(kind,reference_work_id,status,payload_json,created_at) VALUES('REFRESH_LIBRARY',?,'QUEUED','{}',UTC_TIMESTAMP(3))",id);
        boolean effective=false;for(var item:libraries.currentManifest().path("enabledReferenceWorkIds"))if(id.equals(item.asText()))effective=true;
        var receipt=json.valueToTree(Map.of("jobId",Long.toString(job),"requestedEnabled",enabled,"effectiveEnabled",effective,"status","PENDING_SWITCH"));keys.complete(user.userId(),"REFERENCE_ENABLED",key,receipt);return receipt;
    }
}
