package local.campus.review.reference;
import com.fasterxml.jackson.databind.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;

@Service
public class PublicationService {
    private final JdbcTemplate db;private final ObjectMapper json;
    public PublicationService(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
    @Transactional public String publishApprovedVersion(String versionId){
        var version=db.queryForMap("SELECT * FROM submission_version WHERE id=?",versionId);String manuscript=version.get("manuscript_id").toString();
        if(db.queryForObject("SELECT COUNT(*) FROM review_decision WHERE submission_version_id=? AND decision='APPROVE'",Integer.class,versionId)!=1)throw new ApiException(409,"INVALID_STATE","版本尚未通过审核");
        db.update("UPDATE manuscript SET publication_state='PUBLISHED',published_version_id=?,first_published_at=COALESCE(first_published_at,UTC_TIMESTAMP(3)),reprint_allowed=IF(reprint_locked_at IS NULL,true,reprint_allowed),reprint_locked_at=COALESCE(reprint_locked_at,UTC_TIMESTAMP(3)),updated_at=UTC_TIMESTAMP(3) WHERE id=?",versionId,manuscript);
        var existing=db.queryForList("SELECT id FROM reference_work WHERE manuscript_id=? FOR UPDATE",manuscript);
        String work=existing.isEmpty()?Long.toString(SqlSupport.insert(db,"INSERT INTO reference_work(manuscript_id,origin_type,enabled,created_by,created_at) VALUES(?,'PUBLISHED',true,?,UTC_TIMESTAMP(3))",manuscript,version.get("submitted_by"))):existing.getFirst().get("id").toString();
        int number=db.queryForObject("SELECT COALESCE(MAX(revision_no),0)+1 FROM reference_revision WHERE reference_work_id=?",Integer.class,work);
        var metadata=json.createObjectNode().put("sourceType","PUBLISHED").put("submissionId",versionId).put("manuscriptId",manuscript);metadata.set("bodySources",JsonSupport.parse(json,version.get("sources_json").toString()));
        var artifacts=json.createObjectNode().put("plainText",version.get("plain_text").toString()).put("contentSha256",version.get("content_sha256").toString());artifacts.putObject("parts");
        long revision=SqlSupport.insert(db,"INSERT INTO reference_revision(reference_work_id,revision_no,submission_version_id,title,content_json,source_metadata_json,original_published_at,processing_status,artifacts_json,created_at) SELECT ?,?,?,?,?,?,first_published_at,'QUEUED',?,UTC_TIMESTAMP(3) FROM manuscript WHERE id=?",work,number,versionId,version.get("title"),version.get("content_json"),JsonSupport.encode(json,metadata),JsonSupport.encode(json,artifacts),manuscript);
        db.update("INSERT INTO file_binding(file_id,reference_revision_id,node_id,purpose) SELECT file_id,?,node_id,'BODY_IMAGE' FROM file_binding WHERE submission_version_id=? AND purpose='BODY_IMAGE'",revision,versionId);
        db.update("INSERT INTO background_job(kind,reference_revision_id,status,payload_json,created_at) VALUES('PREPARE_REFERENCE',?,'QUEUED','{}',UTC_TIMESTAMP(3))",revision);return work;
    }
    public JsonNode get(String id){
        var rows=db.queryForList("SELECT v.*,m.first_published_at,m.reprint_allowed,o.name AS organization_name FROM manuscript m JOIN submission_version v ON v.id=m.published_version_id JOIN organization o ON o.id=m.organization_id WHERE m.id=? AND m.publication_state='PUBLISHED'",id);
        if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到已发布稿件");var row=rows.getFirst();
        var result=json.createObjectNode().put("manuscriptId",id).put("submissionId",row.get("id").toString()).put("title",row.get("title").toString()).put("schemaVersion",row.get("schema_version").toString()).put("organizationName",row.get("organization_name").toString()).put("publishedAt",((LocalDateTime)row.get("first_published_at")).atOffset(ZoneOffset.UTC).toString()).put("reprintAllowed",(Boolean)row.get("reprint_allowed"));
        result.set("content",JsonSupport.parse(json,row.get("content_json").toString()));result.set("sources",JsonSupport.parse(json,row.get("sources_json").toString()));return result;
    }
    public JsonNode list(int page,int size,String q){
        if(page<1 || size<1 || size>100 || q.length()>200)throw new ApiException(400,"VALIDATION_ERROR","列表参数无效");
        String from=" FROM manuscript m JOIN submission_version v ON v.id=m.published_version_id JOIN organization o ON o.id=m.organization_id WHERE m.publication_state='PUBLISHED' AND v.title LIKE ?";
        var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,"%"+q+"%"));var items=result.putArray("items");
        for(var row:db.queryForList("SELECT m.id,m.first_published_at,v.id AS submission_id,v.title,o.name AS organization_name"+from+" ORDER BY m.first_published_at DESC,m.id DESC LIMIT ? OFFSET ?","%"+q+"%",size,(long)(page-1)*size))items.addObject().put("manuscriptId",row.get("id").toString()).put("submissionId",row.get("submission_id").toString()).put("title",row.get("title").toString()).put("organizationName",row.get("organization_name").toString()).put("publishedAt",((LocalDateTime)row.get("first_published_at")).atOffset(ZoneOffset.UTC).toString());
        return result;
    }
}
