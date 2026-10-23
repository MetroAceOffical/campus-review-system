package local.campus.review.reference;

import local.campus.review.HttpTestSupport;
import local.campus.review.common.RuntimeSettings;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.jdbc.core.JdbcTemplate;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class LibraryGenerationIT extends HttpTestSupport {
    @Autowired JdbcTemplate sql;
    @Autowired LibraryGenerationService libraries;
    @Autowired RuntimeSettings settings;
    @Test void failedBuildKeepsCurrentGeneration() throws Exception {
        String previous=libraries.currentId();
        String ready=libraries.reserve();
        Path directory=settings.runtime().resolve("indexes").resolve(ready);Files.createDirectories(directory);
        String manifest="{\"generationId\":\""+ready+"\",\"documents\":[],\"images\":[],\"enabledReferenceWorkIds\":[]}";
        Files.writeString(directory.resolve("manifest.json"),manifest);
        String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(manifest.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        Files.writeString(directory.resolve("READY"),hash);
        libraries.markReady(ready,hash);libraries.activate(ready,previous);
        String failed=libraries.reserve();libraries.fail(failed,"CONTROLLED_BUILD_FAILURE");
        assertThrows(RuntimeException.class,()->libraries.activate(failed,ready));
        assertEquals(ready,libraries.currentId());
        assertTrue(Files.exists(directory.resolve("manifest.json")));
        String corrupt=libraries.reserve();
        Path bad=settings.runtime().resolve("indexes").resolve(corrupt);Files.createDirectories(bad);
        Files.writeString(bad.resolve("manifest.json"),"{}");Files.writeString(bad.resolve("READY"),"0".repeat(64));
        assertThrows(RuntimeException.class,()->libraries.markReady(corrupt,"0".repeat(64)));
        assertEquals(ready,libraries.currentId());
    }
    @Test void publishedImportDoesNotBecomePublication() throws Exception {
        var admin=login("admin");long before=sql.queryForObject("SELECT COUNT(*) FROM manuscript WHERE publication_state='PUBLISHED'",Long.class);
        String key=UUID.randomUUID().toString();
        String input="{\"title\":\"M06手动参考测试\",\"schemaVersion\":\"1\",\"content\":{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"attrs\":{\"nodeId\":\"p\"},\"content\":[{\"type\":\"text\",\"text\":\"仅用于参考入库事务检查，不发布。\"}]}]},\"sources\":[],\"sourceMetadata\":{\"sourceType\":\"MANUAL\",\"description\":\"明确测试材料\"}}";
        var first=http.perform(csrf(post("/api/references"),admin).header("Idempotency-Key",key).contentType("application/json").content(input))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.processingStatus").value("QUEUED")).andReturn();
        String referenceId=json.readTree(first.getResponse().getContentAsString()).path("data").path("referenceId").asText();
        var dated=json.readTree(input);
        ((com.fasterxml.jackson.databind.node.ObjectNode)dated.path("sourceMetadata")).put("published_at","2025-04-09T11:26:34.154000+00:00");
        var datedResponse=http.perform(csrf(post("/api/references"),admin).header("Idempotency-Key",UUID.randomUUID().toString()).contentType("application/json").content(json.writeValueAsString(dated)))
            .andExpect(status().isOk()).andReturn();
        String datedId=json.readTree(datedResponse.getResponse().getContentAsString()).path("data").path("referenceId").asText();
        assertNotNull(sql.queryForObject("SELECT original_published_at FROM reference_revision WHERE reference_work_id=?",java.time.LocalDateTime.class,datedId));
        http.perform(csrf(post("/api/references"),admin).header("Idempotency-Key",key).contentType("application/json").content(input))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.referenceId").value(referenceId));
        assertEquals(before,sql.queryForObject("SELECT COUNT(*) FROM manuscript WHERE publication_state='PUBLISHED'",Long.class));
        assertEquals(1,sql.queryForObject("SELECT COUNT(*) FROM background_job WHERE kind='PREPARE_REFERENCE' AND reference_revision_id=(SELECT id FROM reference_revision WHERE reference_work_id=?)",Integer.class,referenceId));
    }
}
