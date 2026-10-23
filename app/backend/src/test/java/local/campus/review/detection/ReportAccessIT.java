package local.campus.review.detection;
import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class ReportAccessIT extends HttpTestSupport {
    @Test void queueRequiresReviewerAndDoesNotListUnsubmittedDrafts()throws Exception{
        http.perform(get("/api/reviews").session(login("member1"))).andExpect(status().isForbidden());
        http.perform(get("/api/reviews").session(login("admin"))).andExpect(status().isForbidden());
        http.perform(get("/api/reviews").session(login("reviewer"))).andExpect(status().isOk()).andExpect(jsonPath("$.data.items").isArray());
        http.perform(get("/api/detection-batches/999999/report").session(login("member1"))).andExpect(status().isForbidden());
    }
}
