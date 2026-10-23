package local.campus.review;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import java.nio.file.*;
import java.util.Map;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

public abstract class HttpTestSupport {
    @Autowired protected MockMvc http;
    @Autowired protected ObjectMapper json;
    protected MockHttpSession login(String username) throws Exception {
        var result=http.perform(get("/api/auth/csrf")).andExpect(status().isOk()).andReturn();
        var session=(MockHttpSession)result.getRequest().getSession();
        var token=json.readTree(result.getResponse().getContentAsString()).path("data");
        var accounts=json.readTree(Files.readString(Path.of(System.getenv("CAMPUS_ACCOUNTS_FILE"))));
        http.perform(post("/api/auth/login").session(session).header(token.path("headerName").asText(),token.path("token").asText()).contentType("application/json")
            .content(json.writeValueAsBytes(Map.of("username",username,"password",accounts.path(username).asText())))).andExpect(status().isOk());
        return session;
    }
    protected MockHttpServletRequestBuilder csrf(MockHttpServletRequestBuilder builder,MockHttpSession session) throws Exception {
        var result=http.perform(get("/api/auth/csrf").session(session)).andReturn();
        var token=json.readTree(result.getResponse().getContentAsString()).path("data");
        return builder.session(session).header(token.path("headerName").asText(),token.path("token").asText());
    }
}
