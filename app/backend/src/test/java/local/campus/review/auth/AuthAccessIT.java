package local.campus.review.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.MockMvcPrint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import java.nio.file.*;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class AuthAccessIT {
    @Autowired MockMvc http;
    @Autowired ObjectMapper json;

    private MockHttpSession login(String username, String role) throws Exception {
        var csrf = http.perform(get("/api/auth/csrf")).andExpect(status().isOk()).andReturn();
        var token = json.readTree(csrf.getResponse().getContentAsString()).path("data");
        var accounts = json.readTree(Files.readString(Path.of(System.getenv("CAMPUS_ACCOUNTS_FILE"))));
        var session = (MockHttpSession) csrf.getRequest().getSession(false);
        var oldId = session.getId();
        var result = http.perform(post("/api/auth/login").session(session)
                .header(token.path("headerName").asText(),token.path("token").asText())
                .contentType("application/json").content(json.writeValueAsBytes(Map.of("username",username,"password",accounts.path(username).asText()))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.role").value(role))
                .andExpect(jsonPath("$.data.passwordHash").doesNotExist()).andReturn();
        assertNotEquals(oldId, result.getRequest().getSession().getId());
        return (MockHttpSession) result.getRequest().getSession(false);
    }

    @Test void fourAccountsAndOrganizationPermissions() throws Exception {
        var a = login("member1", "MEMBER");
        var b = login("member2", "MEMBER");
        http.perform(get("/api/auth/me").session(a)).andExpect(status().isOk()).andExpect(jsonPath("$.data.organizations[0].name").value("校学生会"));
        http.perform(get("/api/auth/me").session(b)).andExpect(status().isOk()).andExpect(jsonPath("$.data.organizations[0].name").value("校园融媒体中心"));
        login("reviewer", "REVIEWER"); login("admin", "ADMIN");
    }
    @Test void sessionRequiredAndForgedIdentityIgnored() throws Exception {
        http.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
        http.perform(get("/api/experiments").header("X-User","admin")).andExpect(status().isUnauthorized());
        var session = login("member1", "MEMBER");
        http.perform(get("/api/experiments").session(session).header("X-User","admin")).andExpect(status().isForbidden());
        http.perform(get("/api/references").session(session)).andExpect(status().isForbidden());
    }
    @Test void csrfRequiredAndLogoutInvalidatesSession() throws Exception {
        http.perform(post("/api/auth/login").contentType("application/json").content("{}"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.code").value("CSRF_INVALID"));
        var session = login("member1", "MEMBER");
        http.perform(post("/api/auth/logout").session(session)).andExpect(status().isForbidden());
        var result = http.perform(get("/api/auth/csrf").session(session)).andReturn();
        var token = json.readTree(result.getResponse().getContentAsString()).path("data");
        http.perform(post("/api/auth/logout").session(session).header(token.path("headerName").asText(),token.path("token").asText())).andExpect(status().isOk());
        assertTrue(session.isInvalid());
        http.perform(get("/api/auth/me")).andExpect(status().isUnauthorized());
    }
    @Test void badPasswordDoesNotEstablishSession() throws Exception {
        var result = http.perform(get("/api/auth/csrf")).andReturn();
        var token = json.readTree(result.getResponse().getContentAsString()).path("data");
        var session = (MockHttpSession)result.getRequest().getSession(false);
        http.perform(post("/api/auth/login").session(session).header(token.path("headerName").asText(),token.path("token").asText())
                .contentType("application/json").content("{\"username\":\"member1\",\"password\":\"incorrect\"}"))
                .andExpect(status().isUnauthorized());
        http.perform(get("/api/auth/me").session(session)).andExpect(status().isUnauthorized());
    }
}
