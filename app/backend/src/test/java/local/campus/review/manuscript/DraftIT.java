package local.campus.review.manuscript;

import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class DraftIT extends HttpTestSupport {
    @Test void oldRevisionCannotOverwrite() throws Exception {
        var session=login("member1");
        var created=http.perform(csrf(post("/api/manuscripts"),session).contentType("application/json").content("{\"organizationId\":\"1\"}"))
            .andExpect(status().isOk()).andReturn();
        var id=json.readTree(created.getResponse().getContentAsString()).path("data").path("manuscriptId").asText();
        String payload="{\"expectedRevision\":0,\"title\":\"新保存\",\"schemaVersion\":\"1\",\"content\":{\"type\":\"doc\",\"content\":[]},\"sources\":[]}";
        http.perform(csrf(put("/api/manuscripts/"+id+"/draft"),session).contentType("application/json").content(payload))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.revision").value("1"));
        http.perform(csrf(put("/api/manuscripts/"+id+"/draft"),session).contentType("application/json").content(payload.replace("新保存","旧窗口")))
            .andExpect(status().isConflict()).andExpect(jsonPath("$.code").value("DRAFT_REVISION_CONFLICT"));
        http.perform(get("/api/manuscripts/"+id+"/draft").session(session)).andExpect(status().isOk()).andExpect(jsonPath("$.data.title").value("新保存"));
        var other=login("member2");
        http.perform(get("/api/manuscripts/"+id+"/draft").session(other)).andExpect(status().isNotFound());
        http.perform(csrf(post("/api/manuscripts"),other).contentType("application/json").content("{\"organizationId\":\"1\"}"))
            .andExpect(status().isNotFound());
    }
}
