package local.campus.review.workbench;

import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}","campus.workbench.enabled=false"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class DatasetPurposeIT extends HttpTestSupport {
    @Autowired WorkbenchWorker worker;
    @Autowired JdbcTemplate db;
    @Test void persistsPurposeAndEnqueuesOneApprovalOnlyImportAfterSuccessfulCleaning() throws Exception {
        var session=login("reviewer");
        var file=new MockMultipartFile("file","news.csv","text/csv","id,title,text\na,新闻稿,学校举办新闻写作交流活动。\n".getBytes(StandardCharsets.UTF_8));
        var response=http.perform(csrf(multipart("/api/workbench/datasets").file(file).param("organizationId","1").param("name","用途衔接专用检查").param("kind","NEWS").param("purpose","LIBRARY"),session)).andExpect(status().isOk()).andReturn();
        var dataset=json.readTree(response.getResponse().getContentAsString()).path("data");String id=dataset.path("datasetId").asText();
        http.perform(get("/api/workbench/datasets/"+id).session(session)).andExpect(jsonPath("$.data.purpose").value("LIBRARY"));
        worker.runOne();
        response=http.perform(csrf(post("/api/workbench/datasets/"+id+"/runs"),session).contentType("application/json").content(json.writeValueAsBytes(Map.of("action","CLEAN","versionId",dataset.path("versionId").asText(),"options",Map.of("auto_reference_import",true))))).andExpect(status().isOk()).andReturn();
        String run=json.readTree(response.getResponse().getContentAsString()).path("data").path("runId").asText();
        for(int i=0;i<10&&!"COMPLETED".equals(db.queryForObject("SELECT status FROM ml_run WHERE id=?",String.class,run));i++)worker.runOne();
        assertEquals("COMPLETED",db.queryForObject("SELECT status FROM ml_run WHERE id=?",String.class,run));
        assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM reference_import WHERE dataset_id=?",Integer.class,id));
        assertEquals("PENDING_APPROVAL",db.queryForObject("SELECT status FROM reference_import WHERE dataset_id=?",String.class,id));
        worker.runOne();
        assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM reference_import WHERE dataset_id=?",Integer.class,id));
        http.perform(get("/api/workbench/datasets/"+id).session(session)).andExpect(jsonPath("$.data.referenceImports[0].status").value("PENDING_APPROVAL"));
        var creator=login("member1");http.perform(get("/api/workbench/datasets/"+id).session(creator)).andExpect(status().isForbidden());
    }
}
