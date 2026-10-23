package local.campus.review.review;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.manuscript.*;
import local.campus.review.content.DocumentModels.*;
import local.campus.review.detection.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
class DecisionIT {
    @Autowired JdbcTemplate db;@Autowired ObjectMapper json;@Autowired DraftService drafts;
    @Autowired SubmissionService submissions;@Autowired ReviewService reviews;@Autowired AttemptRepository attempts;
    private CurrentUser user(String name,CurrentUser.Role role){return new CurrentUser(db.queryForObject("SELECT id FROM app_user WHERE username=?",String.class,name),name,role,role==CurrentUser.Role.MEMBER?Set.of("1"):Set.of(),List.of());}
    @Test void concurrentDecisionPublishesSnapshotOnceAndLateReportDoesNotChangeDecision()throws Exception{
        var member=user("member1",CurrentUser.Role.MEMBER);var reviewer=user("reviewer",CurrentUser.Role.REVIEWER);
        String manuscript=drafts.create(member,"1","test").get("manuscriptId").toString();
        var content=json.readTree("{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"attrs\":{\"nodeId\":\"p\"},\"content\":[{\"type\":\"text\",\"text\":\"通过后发布的不可变快照\"}]}]}");
        var receipt=submissions.submit(member,manuscript,UUID.randomUUID().toString(),0,new DocumentInput("并发审核测试","1",content,List.of()));
        String version=receipt.path("submissionId").asText(),batch=receipt.path("batchId").asText();
        String item=db.queryForObject("SELECT id FROM detection_item WHERE batch_id=?",String.class,batch);String attempt=attempts.start(item,json.createObjectNode());
        int success=0;
        try(var executor=Executors.newFixedThreadPool(2)){
            var gate=new CountDownLatch(1);var futures=new ArrayList<Future<Boolean>>();
            for(int i=0;i<2;i++)futures.add(executor.submit(()->{gate.await();try{reviews.decide(reviewer,version,UUID.randomUUID().toString(),"APPROVE","");return true;}catch(local.campus.review.common.ApiException conflict){assertEquals("ALREADY_DECIDED",conflict.code);return false;}}));
            gate.countDown();for(var future:futures)if(future.get())success++;
        }
        assertEquals(1,success);assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM review_decision WHERE submission_version_id=?",Integer.class,version));
        String decision=db.queryForObject("SELECT detection_snapshot_json FROM review_decision WHERE submission_version_id=?",String.class,version);
        assertTrue(decision.contains("RUNNING"));
        assertTrue(attempts.completeIfCurrent(attempt,json.createObjectNode().put("status","COMPLETED")));
        assertEquals(decision,db.queryForObject("SELECT detection_snapshot_json FROM review_decision WHERE submission_version_id=?",String.class,version));
        assertEquals(version,db.queryForObject("SELECT published_version_id FROM manuscript WHERE id=?",String.class,manuscript));
        assertEquals(true,db.queryForObject("SELECT reprint_allowed FROM manuscript WHERE id=?",Boolean.class,manuscript));
        assertNotNull(db.queryForObject("SELECT first_published_at FROM manuscript WHERE id=?",java.time.LocalDateTime.class,manuscript));
        assertEquals("通过后发布的不可变快照",json.readTree(db.queryForObject("SELECT r.artifacts_json FROM reference_revision r JOIN reference_work w ON w.id=r.reference_work_id WHERE w.manuscript_id=?",String.class,manuscript)).path("plainText").asText());
    }
    @Test void returnIsIdempotentAndNextSubmissionKeepsOldSnapshot()throws Exception{
        var member=user("member1",CurrentUser.Role.MEMBER);var reviewer=user("reviewer",CurrentUser.Role.REVIEWER);
        String manuscript=drafts.create(member,"1","test").get("manuscriptId").toString();
        var content=json.readTree("{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"attrs\":{\"nodeId\":\"p\"},\"content\":[{\"type\":\"text\",\"text\":\"退回前的原始正文\"}]}]}");
        var input=new DocumentInput("退回测试","1",content,List.of());var first=submissions.submit(member,manuscript,UUID.randomUUID().toString(),0,input);String version=first.path("submissionId").asText();
        assertThrows(local.campus.review.common.ApiException.class,()->reviews.decide(reviewer,version,UUID.randomUUID().toString(),"RETURN"," "));
        String key=UUID.randomUUID().toString();var decision=reviews.decide(reviewer,version,key,"RETURN","请补充来源");assertEquals(decision,reviews.decide(reviewer,version,key,"RETURN","请补充来源"));
        assertEquals("NOT_PUBLISHED",db.queryForObject("SELECT publication_state FROM manuscript WHERE id=?",String.class,manuscript));
        assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM reference_work WHERE manuscript_id=?",Integer.class,manuscript));
        var changed=json.readTree(content.toString().replace("退回前的原始正文","退回后新正文"));
        var second=submissions.submit(member,manuscript,UUID.randomUUID().toString(),1,new DocumentInput("再次送审","1",changed,List.of()));
        assertEquals(2,second.path("versionNo").asInt());assertEquals("退回前的原始正文",db.queryForObject("SELECT plain_text FROM submission_version WHERE id=?",String.class,version));
        assertEquals("退回后新正文",db.queryForObject("SELECT plain_text FROM submission_version WHERE id=?",String.class,second.path("submissionId").asText()));
    }
}
