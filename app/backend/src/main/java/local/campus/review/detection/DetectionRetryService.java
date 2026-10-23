package local.campus.review.detection;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;

@Service
public class DetectionRetryService {
    private final JdbcTemplate db;private final ObjectMapper json;private final IdempotencyStore keys;
    public DetectionRetryService(JdbcTemplate db,ObjectMapper json,IdempotencyStore keys){this.db=db;this.json=json;this.keys=keys;}
    @Transactional public JsonNode retry(CurrentUser user,String itemId,String key,String expectedAttempt){
        AccessPolicy.requireReviewer(user);
        if(expectedAttempt==null)throw new ApiException(400,"VALIDATION_ERROR","缺少预期执行编号");
        var cached=keys.begin(user.userId(),"DETECTION_RETRY",key,JsonSupport.hash(json,Map.of("itemId",itemId,"expectedAttemptId",expectedAttempt)));if(cached!=null)return cached;
        var rows=db.queryForList("SELECT batch_id FROM detection_item WHERE id=?",itemId);if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到检测项");
        var batch=db.queryForMap("SELECT b.*,v.lifecycle_status FROM detection_batch b JOIN submission_version v ON v.id=b.submission_version_id WHERE b.id=? FOR UPDATE",rows.getFirst().get("batch_id"));
        if(batch.get("cancelled_at")!=null || Set.of("WITHDRAWN","SUPERSEDED").contains(batch.get("lifecycle_status")))throw new ApiException(409,"BATCH_CANCELLED","该批次已取消，不能重试");
        var item=db.queryForMap("SELECT * FROM detection_item WHERE id=? FOR UPDATE",itemId);
        if(!Set.of("FAILED","INTERRUPTED").contains(item.get("status")) || !expectedAttempt.equals(Objects.toString(item.get("active_attempt_id"),"")))throw new ApiException(409,"ATTEMPT_CONFLICT","执行状态已变化，请刷新后重试");
        db.update("UPDATE detection_item SET active_attempt_id=NULL,status='QUEUED',updated_at=UTC_TIMESTAMP(3) WHERE id=?",itemId);
        db.update("UPDATE detection_batch SET status='QUEUED',finished_at=NULL WHERE id=?",batch.get("id"));
        long job=SqlSupport.insert(db,"INSERT INTO background_job(kind,item_id,status,payload_json,created_at) VALUES('RETRY_ITEM',?,'QUEUED','{}',UTC_TIMESTAMP(3))",itemId);
        var result=json.valueToTree(Map.of("jobId",Long.toString(job),"itemId",itemId,"status","QUEUED"));keys.complete(user.userId(),"DETECTION_RETRY",key,result);return result;
    }
}
