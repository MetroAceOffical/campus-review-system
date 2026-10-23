package local.campus.review.manuscript;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.time.*;
import java.util.*;

@Service
public class ManuscriptQueryService {
    private final JdbcTemplate db;private final ObjectMapper json;
    public ManuscriptQueryService(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
    public JsonNode list(CurrentUser user,int page,int size,String q,String status){
        if(user.role()!=CurrentUser.Role.MEMBER)throw new ApiException(403,"ACCESS_DENIED","无权访问组织稿件");
        if(page<1 || size<1 || size>100 || q.length()>200 || (!status.isBlank() && !Set.of("DRAFT","PENDING","RETURNED","APPROVED","REJECTED").contains(status)))throw new ApiException(400,"VALIDATION_ERROR","列表参数无效");
        String from=" FROM manuscript m JOIN manuscript_draft d ON d.manuscript_id=m.id JOIN organization_member om ON om.organization_id=m.organization_id JOIN organization o ON o.id=m.organization_id WHERE om.user_id=? AND om.enabled=true AND o.enabled=true AND m.deleted_at IS NULL AND d.title LIKE ? AND (?='' OR m.status=?)";
        var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,user.userId(),"%"+q+"%",status,status));var items=result.putArray("items");
        for(var row:db.queryForList("SELECT m.*,d.title,d.revision,o.name AS organization_name"+from+" ORDER BY m.updated_at DESC,m.id DESC LIMIT ? OFFSET ?",user.userId(),"%"+q+"%",status,status,size,(long)(page-1)*size)){
            var item=items.addObject().put("manuscriptId",row.get("id").toString()).put("title",row.get("title").toString()).put("status",row.get("status").toString()).put("publicationState",row.get("publication_state").toString()).put("organizationName",row.get("organization_name").toString()).put("draftRevision",row.get("revision").toString()).put("updatedAt",((LocalDateTime)row.get("updated_at")).atOffset(ZoneOffset.UTC).toString());
            if(row.get("current_submission_id")==null)item.putNull("currentSubmissionId");else item.put("currentSubmissionId",row.get("current_submission_id").toString());
        }
        return result;
    }
    public JsonNode history(CurrentUser user,String id){
        var rows=db.queryForList("SELECT * FROM manuscript WHERE id=? AND deleted_at IS NULL",id);if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到稿件");var manuscript=rows.getFirst();
        if(user.role()!=CurrentUser.Role.REVIEWER)AccessPolicy.requireOrganization(user,manuscript.get("organization_id").toString());
        var result=json.createObjectNode().put("manuscriptId",id).put("status",manuscript.get("status").toString());var items=result.putArray("items");
        for(var row:db.queryForList("SELECT v.id,v.version_no,v.title,v.lifecycle_status,v.submitted_at,r.decision,r.reason,b.id AS batch_id FROM submission_version v LEFT JOIN review_decision r ON r.submission_version_id=v.id LEFT JOIN detection_batch b ON b.submission_version_id=v.id AND b.batch_no=(SELECT MAX(x.batch_no) FROM detection_batch x WHERE x.submission_version_id=v.id) WHERE v.manuscript_id=? ORDER BY v.version_no DESC",id)){
            var item=items.addObject().put("submissionId",row.get("id").toString()).put("versionNo",((Number)row.get("version_no")).intValue()).put("title",row.get("title").toString()).put("lifecycleStatus",row.get("lifecycle_status").toString()).put("submittedAt",((LocalDateTime)row.get("submitted_at")).atOffset(ZoneOffset.UTC).toString());
            if(row.get("batch_id")==null)item.putNull("batchId");else item.put("batchId",row.get("batch_id").toString());item.put("decision",Objects.toString(row.get("decision"),"")).put("reason",Objects.toString(row.get("reason"),""));
        }
        return result;
    }
}
