package local.campus.review.review;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.detection.DetectionQueryService;
import local.campus.review.reference.PublicationService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;

@Service
public class ReviewService {
    private final JdbcTemplate db;private final ObjectMapper json;private final IdempotencyStore keys;
    private final PublicationService publications;private final DetectionQueryService queries;
    public ReviewService(JdbcTemplate db,ObjectMapper json,IdempotencyStore keys,PublicationService publications,DetectionQueryService queries){this.db=db;this.json=json;this.keys=keys;this.publications=publications;this.queries=queries;}
    @Transactional public JsonNode decide(CurrentUser user,String versionId,String key,String decision,String reason){return decide(user,versionId,key,decision,reason,null);}
    @Transactional public JsonNode decide(CurrentUser user,String versionId,String key,String decision,String reason,String checkId){
        AccessPolicy.requireReviewer(user);String explanation=reason==null?"":reason;
        if(decision==null || !Set.of("APPROVE","RETURN","REJECT").contains(decision) || (!"APPROVE".equals(decision) && explanation.isBlank()) || explanation.codePointCount(0,explanation.length())>4000)throw new ApiException(400,"VALIDATION_ERROR","请选择有效决定，退回或拒绝必须填写理由");
        var versions=db.queryForList("SELECT manuscript_id FROM submission_version WHERE id=?",versionId);if(versions.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到送审版本");
        String manuscriptId=versions.getFirst().get("manuscript_id").toString();var manuscript=db.queryForMap("SELECT * FROM manuscript WHERE id=? FOR UPDATE",manuscriptId);
        var identity=new LinkedHashMap<String,Object>(Map.of("versionId",versionId,"decision",decision,"reason",explanation));if(checkId!=null)identity.put("checkId",checkId);
        var cached=keys.begin(user.userId(),"DECIDE",key,JsonSupport.hash(json,identity));if(cached!=null)return cached;
        var version=db.queryForMap("SELECT * FROM submission_version WHERE id=? FOR UPDATE",versionId);
        if(!"PENDING".equals(manuscript.get("status")) || !versionId.equals(Objects.toString(manuscript.get("current_submission_id"),"")) || !"PENDING".equals(version.get("lifecycle_status")))throw new ApiException(409,"ALREADY_DECIDED","版本已经处理或不再待审");
        String batch=db.queryForObject("SELECT id FROM detection_batch WHERE submission_version_id=? ORDER BY batch_no DESC LIMIT 1",String.class,versionId);
        var evidence=(com.fasterxml.jackson.databind.node.ObjectNode)queries.snapshot(batch);
        if(checkId!=null){var checks=db.queryForList("SELECT id,input_sha256,payload_json,result_json FROM document_check WHERE id=? AND submission_version_id=? AND kind='CONTENT' AND status='COMPLETED'",checkId,versionId);if(checks.isEmpty())throw new ApiException(409,"CHECK_NOT_READY","请选择本版稿件已完成的复检记录");var row=checks.getFirst();var check=json.createObjectNode().put("checkId",checkId).put("inputHash",row.get("input_sha256").toString());check.set("contentProfile",JsonSupport.parse(json,row.get("payload_json").toString()).path("contentProfile"));check.set("result",JsonSupport.parse(json,row.get("result_json").toString()));evidence.set("selectedContentCheck",check);}
        long id=SqlSupport.insert(db,"INSERT INTO review_decision(submission_version_id,reviewer_id,decision,reason,detection_snapshot_json,decided_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3))",versionId,user.userId(),decision,explanation,JsonSupport.encode(json,evidence));
        String status=switch(decision){case "APPROVE"->"APPROVED";case "RETURN"->"RETURNED";default->"REJECTED";};
        db.update("UPDATE manuscript SET status=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?",status,manuscriptId);db.update("UPDATE submission_version SET lifecycle_status='DECIDED' WHERE id=?",versionId);
        if("APPROVE".equals(decision))publications.publishApprovedVersion(versionId);
        var details=json.createObjectNode().put("schemaVersion","1").put("actorName",user.displayName()).put("decision",decision).put("reason",explanation).put("organizationName",db.queryForObject("SELECT name FROM organization WHERE id=?",String.class,manuscript.get("organization_id")));
        db.update("INSERT INTO operation_log(actor_id,organization_id,object_type,object_id,version_id,operation,details_json,created_at) VALUES(?,?,'MANUSCRIPT',?,?,'DECIDED',?,UTC_TIMESTAMP(3))",user.userId(),manuscript.get("organization_id"),manuscriptId,versionId,JsonSupport.encode(json,details));
        var receipt=json.createObjectNode().put("decisionId",Long.toString(id)).put("status",status);if("APPROVE".equals(decision)){receipt.put("publishedVersionId",versionId).put("referenceProcessingStatus","QUEUED");}else receipt.putNull("publishedVersionId");
        keys.complete(user.userId(),"DECIDE",key,receipt);return receipt;
    }
}
