package local.campus.review.manuscript;
import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import java.util.UUID;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class SubmissionIT extends HttpTestSupport {
    @Test void submitIdempotenceConflictAndSnapshotAccess()throws Exception{
        var member=login("member1");
        var created=http.perform(csrf(post("/api/manuscripts"),member).contentType("application/json").content("{\"organizationId\":\"1\"}" )).andExpect(status().isOk()).andReturn();
        String id=json.readTree(created.getResponse().getContentAsString()).path("data").path("manuscriptId").asText();
        String payload="{\"expectedDraftRevision\":0,\"title\":\"M08事务测试\",\"schemaVersion\":\"1\",\"content\":{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"attrs\":{\"nodeId\":\"p\"},\"content\":[{\"type\":\"text\",\"text\":\"这是不可变送审正文，测试内容。\"}]}]},\"sources\":[]}";
        String key=UUID.randomUUID().toString();
        var first=http.perform(csrf(post("/api/manuscripts/"+id+"/submissions"),member).header("Idempotency-Key",key).contentType("application/json").content(payload)).andExpect(status().isOk()).andReturn();
        String submission=json.readTree(first.getResponse().getContentAsString()).path("data").path("submissionId").asText();
        String batch=json.readTree(first.getResponse().getContentAsString()).path("data").path("batchId").asText();
        http.perform(csrf(post("/api/manuscripts/"+id+"/submissions"),member).header("Idempotency-Key",key).contentType("application/json").content(payload)).andExpect(status().isOk()).andExpect(jsonPath("$.data.submissionId").value(submission));
        http.perform(csrf(post("/api/manuscripts/"+id+"/submissions"),member).header("Idempotency-Key",key).contentType("application/json").content(payload.replace("M08事务测试","内容被改动"))).andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("IDEMPOTENCY_CONFLICT"));
        http.perform(get("/api/submissions/"+submission).session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.title").value("M08事务测试"));
        http.perform(get("/api/submissions/"+submission).session(login("member2"))).andExpect(status().isNotFound());
        http.perform(get("/api/detection-batches/"+batch+"/progress").session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.items[0].evidence").doesNotExist());
        http.perform(get("/api/detection-batches/"+batch+"/report").session(member)).andExpect(status().isForbidden());
        http.perform(get("/api/detection-batches/"+batch+"/report").session(login("reviewer"))).andExpect(status().isOk());
        var second=http.perform(csrf(post("/api/manuscripts"),member).contentType("application/json").content("{\"organizationId\":\"1\"}")).andReturn();
        String other=json.readTree(second.getResponse().getContentAsString()).path("data").path("manuscriptId").asText();
        http.perform(csrf(post("/api/manuscripts/"+other+"/submissions"),member).header("Idempotency-Key",UUID.randomUUID().toString()).contentType("application/json").content(payload.replace("Revision\":0","Revision\":1"))).andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("DRAFT_REVISION_CONFLICT"));
    }
}
