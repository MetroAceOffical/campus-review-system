package local.campus.review.review;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.time.*;
import java.util.*;

@Service
public class ReviewQueryService {
    private final JdbcTemplate db;private final ObjectMapper json;
    public ReviewQueryService(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
    public JsonNode list(CurrentUser user,int page,int size,String q,String status){
        AccessPolicy.requireReviewer(user);
        if(page<1 || size<1 || size>100 || q.length()>200 || !Set.of("","PENDING","DECIDED").contains(status))throw new ApiException(400,"VALIDATION_ERROR","列表参数无效");
        String from=" FROM submission_version v JOIN manuscript m ON m.current_submission_id=v.id JOIN organization o ON o.id=m.organization_id LEFT JOIN review_decision r ON r.submission_version_id=v.id LEFT JOIN detection_batch b ON b.submission_version_id=v.id AND b.batch_no=(SELECT MAX(x.batch_no) FROM detection_batch x WHERE x.submission_version_id=v.id) WHERE v.title LIKE ? AND (?='' OR v.lifecycle_status=?)";
        var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,"%"+q+"%",status,status));var items=result.putArray("items");
        for(var row:db.queryForList("SELECT v.id,v.manuscript_id,v.title,v.version_no,v.submitted_at,m.status,o.name AS organization_name,r.decision,b.status AS detection_status"+from+" ORDER BY v.submitted_at DESC,v.id DESC LIMIT ? OFFSET ?","%"+q+"%",status,status,size,(long)(page-1)*size)){
            items.addObject().put("submissionId",row.get("id").toString()).put("manuscriptId",row.get("manuscript_id").toString()).put("title",row.get("title").toString()).put("versionNo",((Number)row.get("version_no")).intValue()).put("organizationName",row.get("organization_name").toString()).put("status",row.get("status").toString()).put("decision",Objects.toString(row.get("decision"),"")).put("detectionStatus",Objects.toString(row.get("detection_status"),"QUEUED")).put("submittedAt",((LocalDateTime)row.get("submitted_at")).atOffset(ZoneOffset.UTC).toString());
        }
        return result;
    }
}
