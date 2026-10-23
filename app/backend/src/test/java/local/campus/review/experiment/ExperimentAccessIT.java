package local.campus.review.experiment;

import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class ExperimentAccessIT extends HttpTestSupport {
    @Test void onlyAdminCanReadFrozenMetricsAndValidationHistory()throws Exception{
        var admin=login("admin");String base="/api/experiments/pawsx-zh-round2";
        http.perform(get("/api/experiments").session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.experiments[0].models.length()").value(6));
        http.perform(get(base+"/metrics").param("testSet","official_test").session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.values.models.bert.macro_f1").value(.7369837959240795));
        http.perform(get(base+"/metrics").param("testSet","test_no_val_overlap").session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.values.n").value(1527));
        http.perform(get(base+"/history").session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.values.split").value("validation"));
        http.perform(get(base+"/search").session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.values.configurations.length()").value(20));
        http.perform(get(base+"/metrics").param("testSet","made-up").session(admin)).andExpect(status().isBadRequest());
        for(String user:new String[]{"reviewer","member1","member2"})for(String path:new String[]{"",base.substring(16),base.substring(16)+"/curves"})
            http.perform(get("/api/experiments"+path).session(login(user))).andExpect(status().isForbidden());
    }
}
