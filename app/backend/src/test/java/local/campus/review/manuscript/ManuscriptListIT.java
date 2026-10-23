package local.campus.review.manuscript;
import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class ManuscriptListIT extends HttpTestSupport {
    @Test void listAndDraftDeletionRespectOrganizationAndState()throws Exception{
        var member=login("member1");var other=login("member2");
        var response=http.perform(csrf(post("/api/manuscripts"),member).contentType("application/json").content("{\"organizationId\":\"1\",\"title\":\"M09唯一列表夹具\"}")).andReturn();
        String id=json.readTree(response.getResponse().getContentAsString()).path("data").path("manuscriptId").asText();
        http.perform(get("/api/manuscripts?q=M09唯一列表夹具").session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.items[0].manuscriptId").value(id));
        http.perform(get("/api/manuscripts?q=M09唯一列表夹具").session(other)).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        http.perform(csrf(delete("/api/manuscripts/"+id),other)).andExpect(status().isNotFound());
        http.perform(csrf(delete("/api/manuscripts/"+id),member)).andExpect(status().isOk());
        http.perform(get("/api/manuscripts/"+id+"/draft").session(member)).andExpect(status().isNotFound());
        http.perform(get("/api/manuscripts/"+id+"/submissions").session(other)).andExpect(status().isNotFound());
    }
}
