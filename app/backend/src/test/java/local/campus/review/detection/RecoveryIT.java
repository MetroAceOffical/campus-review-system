package local.campus.review.detection;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.SqlSupport;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
class RecoveryIT {
    @Autowired JdbcTemplate db;@Autowired ObjectMapper json;@Autowired DetectionService detection;@Autowired AttemptRepository attempts;@Autowired RecoveryService recovery;@Autowired ProcessSupervisor supervisor;
    @MockitoBean DetectorClient client;
    @BeforeEach void isolate(){assertEquals("campus_review_midterm_test",db.queryForObject("SELECT DATABASE()",String.class));db.update("UPDATE background_job SET status='INTERRUPTED' WHERE status IN ('QUEUED','WAITING_SERVICE','RUNNING')");when(client.health(false)).thenReturn(json.createObjectNode().put("ready",true).put("busy",false).put("runId","main-test"));when(client.health(true)).thenReturn(json.createObjectNode().put("ready",true).put("busy",false).put("runId","ocr-test"));}
    String batch(){return detection.createFormalBatch(DetectionFixtures.version(db,"{\"type\":\"doc\",\"content\":[]}"),"a".repeat(64));}
    @Test void restartKeepsCompletedResultsAndLateAttemptDoesNotOverwriteRetry(){
        String batch=batch(),text=db.queryForObject("SELECT id FROM detection_item WHERE batch_id=?",String.class,batch);
        String done=attempts.start(text,json.createObjectNode());attempts.completeIfCurrent(done,json.createObjectNode().put("status","COMPLETED").put("evidenceId","retained"));
        String unfinished=Long.toString(SqlSupport.insert(db,"INSERT INTO detection_item(batch_id,type,target_key,image_node_id,status,updated_at) VALUES(?,'IMAGE','fixture','fixture','QUEUED',UTC_TIMESTAMP(3))",batch));
        String interrupted=attempts.start(unfinished,json.createObjectNode());
        attempts.checkpointIfCurrent(interrupted,json.createObjectNode().put("checkpoint","kept"));
        db.update("UPDATE background_job SET status='RUNNING',owner_run_id='old-run' WHERE batch_id=?",batch);
        assertTrue(recovery.recoverPreviousRun("new-run"));
        assertEquals(done,db.queryForObject("SELECT active_attempt_id FROM detection_item WHERE id=?",String.class,text));
        assertEquals("COMPLETED",db.queryForObject("SELECT status FROM detection_item WHERE id=?",String.class,text));
        assertEquals("INTERRUPTED",db.queryForObject("SELECT status FROM detection_attempt WHERE id=?",String.class,interrupted));
        assertEquals("kept",jsonValue(interrupted,"checkpoint"));
        assertEquals("QUEUED",db.queryForObject("SELECT status FROM detection_item WHERE id=?",String.class,unfinished));
        String retry=attempts.start(unfinished,json.createObjectNode());assertFalse(attempts.completeIfCurrent(interrupted,json.createObjectNode().put("late",true)));
        assertEquals(retry,db.queryForObject("SELECT active_attempt_id FROM detection_item WHERE id=?",String.class,unfinished));
    }
    String jsonValue(String attempt,String field){try{return json.readTree(db.queryForObject("SELECT result_json FROM detection_attempt WHERE id=?",String.class,attempt)).path(field).asText();}catch(Exception e){throw new RuntimeException(e);}}
    @Test void timeoutDoesNotDispatchIntoBusyProcess(){
        String batch=batch(),item=db.queryForObject("SELECT id FROM detection_item WHERE batch_id=?",String.class,batch);String attempt=attempts.start(item,json.createObjectNode());db.update("UPDATE background_job SET status='RUNNING',owner_run_id='old-run' WHERE batch_id=?",batch);
        when(client.health(false)).thenReturn(json.createObjectNode().put("ready",true).put("busy",true).put("runId","busy"));
        assertFalse(supervisor.ensureReady(false));assertFalse(recovery.recoverPreviousRun("new-run"));assertEquals("RUNNING",db.queryForObject("SELECT status FROM detection_attempt WHERE id=?",String.class,attempt));
        attempts.failIfCurrent(attempt,"DETECTOR_TIMEOUT","timed out");assertEquals("TIMED_OUT",db.queryForObject("SELECT status FROM detection_attempt WHERE id=?",String.class,attempt));assertEquals("FAILED",db.queryForObject("SELECT status FROM detection_item WHERE id=?",String.class,item));
    }
    @Test void cancelledBatchIsNotAutomaticallyRetried(){
        String batch=batch(),item=db.queryForObject("SELECT id FROM detection_item WHERE batch_id=?",String.class,batch);String attempt=attempts.start(item,json.createObjectNode());db.update("UPDATE detection_batch SET cancelled_at=UTC_TIMESTAMP(3) WHERE id=?",batch);db.update("UPDATE background_job SET status='RUNNING',owner_run_id='old-run' WHERE batch_id=?",batch);
        assertTrue(recovery.recoverPreviousRun("new-run"));assertEquals("CANCELLED",db.queryForObject("SELECT status FROM detection_attempt WHERE id=?",String.class,attempt));assertEquals("CANCELLED",db.queryForObject("SELECT status FROM background_job WHERE batch_id=?",String.class,batch));
    }
}
