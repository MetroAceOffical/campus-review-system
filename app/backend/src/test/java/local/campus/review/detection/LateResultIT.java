package local.campus.review.detection;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
class LateResultIT {
    @Autowired JdbcTemplate db;@Autowired ObjectMapper json;
    @Autowired DetectionService detection;@Autowired AttemptRepository attempts;
    @Autowired DetectionRetryService retries;
    private String[] fixture(){
        String version=DetectionFixtures.version(db,"{\"type\":\"doc\",\"content\":[]}");
        String batch=detection.createFormalBatch(version,"a".repeat(64));
        String item=db.queryForObject("SELECT id FROM detection_item WHERE batch_id=? AND type='TEXT'",String.class,batch);
        return new String[]{version,batch,item};
    }
    @Test void decidedVersionStillAcceptsResult(){
        var f=fixture();String attempt=attempts.start(f[2],json.createObjectNode());
        db.update("UPDATE submission_version SET lifecycle_status='DECIDED' WHERE id=?",f[0]);
        assertTrue(attempts.completeIfCurrent(attempt,json.createObjectNode().put("status","COMPLETED")));
    }
    @Test void cancelledBatchRejectsLateResult(){
        var f=fixture();String attempt=attempts.start(f[2],json.createObjectNode());
        db.update("UPDATE detection_batch SET cancelled_at=UTC_TIMESTAMP(3),cancel_reason='WITHDRAWN' WHERE id=?",f[1]);
        assertFalse(attempts.completeIfCurrent(attempt,json.createObjectNode().put("status","COMPLETED")));
        assertEquals("CANCELLED",db.queryForObject("SELECT status FROM detection_attempt WHERE id=?",String.class,attempt));
    }
    @Test void oldAttemptCannotReplaceNewAndFailureKeepsOtherResults(){
        var f=fixture();String old=attempts.start(f[2],json.createObjectNode());
        attempts.failIfCurrent(old,"CONTROLLED","fixture");
        db.update("UPDATE detection_item SET status='QUEUED',active_attempt_id=NULL WHERE id=?",f[2]);
        String current=attempts.start(f[2],json.createObjectNode());
        assertFalse(attempts.completeIfCurrent(old,json.createObjectNode().put("status","COMPLETED")));
        assertTrue(attempts.completeIfCurrent(current,json.createObjectNode().put("status","COMPLETED")));
        assertEquals(current,db.queryForObject("SELECT active_attempt_id FROM detection_item WHERE id=?",String.class,f[2]));
    }
    @Test void retryIsIdempotentAndRequiresExpectedFailedAttempt(){
        var f=fixture();String attempt=attempts.start(f[2],json.createObjectNode());attempts.failIfCurrent(attempt,"CONTROLLED","fixture");
        var reviewer=new local.campus.review.auth.CurrentUser(db.queryForObject("SELECT id FROM app_user WHERE username='reviewer'",String.class),"reviewer",local.campus.review.auth.CurrentUser.Role.REVIEWER,java.util.Set.of(),java.util.List.of());
        assertThrows(local.campus.review.common.ApiException.class,()->retries.retry(reviewer,f[2],java.util.UUID.randomUUID().toString(),"0"));
        String key=java.util.UUID.randomUUID().toString();var first=retries.retry(reviewer,f[2],key,attempt);
        assertEquals(first,retries.retry(reviewer,f[2],key,attempt));
        assertEquals("QUEUED",db.queryForObject("SELECT status FROM detection_item WHERE id=?",String.class,f[2]));
        assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM background_job WHERE kind='RETRY_ITEM' AND item_id=?",Integer.class,f[2]));
    }
}
