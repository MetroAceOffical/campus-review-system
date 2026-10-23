package local.campus.review.reference;
import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import java.util.UUID;
import java.util.*;
import java.nio.file.*;
import java.security.MessageDigest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import local.campus.review.detection.DetectorClient;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.RuntimeSettings;
import local.campus.review.content.FileService;
import local.campus.review.content.DocumentModels;
import org.springframework.mock.web.MockMultipartFile;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class ReferencePublicationIT extends HttpTestSupport {
    @Autowired JdbcTemplate db;@Autowired RuntimeSettings settings;@Autowired FileService files;
    @Autowired ReferenceService references;@Autowired ReferenceProcessor processor;
    @MockitoBean DetectorClient client;
    @Test void manualReferenceSearchDoesNotCreatePublicationAndViewIsAdminOnly()throws Exception{
        var admin=login("admin");String title="M11-"+UUID.randomUUID();
        String input="{\"title\":\""+title+"\",\"schemaVersion\":\"1\",\"content\":{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"attrs\":{\"nodeId\":\"p\"},\"content\":[{\"type\":\"text\",\"text\":\"M11明确参考材料，仅检验管理接口。\"}]}]},\"sources\":[],\"sourceMetadata\":{\"sourceType\":\"MANUAL\",\"description\":\"测试来源\"}}";
        var created=http.perform(csrf(post("/api/references"),admin).header("Idempotency-Key",UUID.randomUUID().toString()).contentType("application/json").content(input)).andExpect(status().isOk()).andReturn();
        String id=json.readTree(created.getResponse().getContentAsString()).path("data").path("referenceId").asText();
        http.perform(get("/api/references").param("q",title).session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(1)).andExpect(jsonPath("$.data.items[0].title").value(title));
        http.perform(get("/api/references/"+id).session(admin)).andExpect(status().isOk()).andExpect(jsonPath("$.data.title").value(title));
        http.perform(get("/api/references/"+id).session(login("member1"))).andExpect(status().isForbidden());
        for(String user:new String[]{"admin","reviewer","member1","member2"})http.perform(get("/api/publications").param("q",title).session(login(user))).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(0));
        http.perform(csrf(patch("/api/references/"+id+"/enabled"),admin).header("Idempotency-Key",UUID.randomUUID().toString()).contentType("application/json").content("{\"enabled\":false}")).andExpect(status().isAccepted()).andExpect(jsonPath("$.data.status").value("PENDING_SWITCH"));
    }
    @Test void imageFailureWithEmptyOcrHasNoUsablePart()throws Exception{
        String adminId=db.queryForObject("SELECT id FROM app_user WHERE username='admin'",String.class);
        var admin=new CurrentUser(adminId,"admin",CurrentUser.Role.ADMIN,Set.of(),List.of());
        var output=new java.io.ByteArrayOutputStream();javax.imageio.ImageIO.write(new java.awt.image.BufferedImage(2,2,java.awt.image.BufferedImage.TYPE_INT_RGB),"png",output);
        var upload=files.upload(admin,new MockMultipartFile("file","M11-partial.png","image/png",output.toByteArray()));
        var document=json.createObjectNode().put("type","doc");document.putArray("content").addObject().put("type","campusImage").putObject("attrs").put("nodeId","image").put("fileId",upload.fileId()).put("caption","").put("origin","ORIGINAL").put("sourceUrl","");
        var created=references.create(admin,UUID.randomUUID().toString(),new ReferenceService.ReferenceInput("M11无可用部分测试","1",document,List.<DocumentModels.Source>of(),json.createObjectNode().put("sourceType","MANUAL").put("description","受控特征失败测试")));
        String revision=created.path("revisionId").asText();
        db.update("UPDATE reference_revision SET processing_status='PREPARED',artifacts_json=? WHERE id=?","{\"plainText\":\"\",\"parts\":{\"BODY\":{\"status\":\"NOT_APPLICABLE\"},\"OCR:image\":{\"status\":\"AVAILABLE\",\"result\":{\"ocrStatus\":\"EMPTY\",\"combinedText\":\"\"}}}}",revision);
        var withBody=document.deepCopy();var paragraph=json.createObjectNode().put("type","paragraph");paragraph.putObject("attrs").put("nodeId","body");paragraph.putArray("content").addObject().put("type","text").put("text","M11部分可用的参考正文".repeat(10));((com.fasterxml.jackson.databind.node.ArrayNode)withBody.path("content")).insert(0,paragraph);
        String partialTitle="M11部分可用-"+UUID.randomUUID();var partial=references.create(admin,UUID.randomUUID().toString(),new ReferenceService.ReferenceInput(partialTitle,"1",withBody,List.<DocumentModels.Source>of(),json.createObjectNode().put("sourceType","MANUAL").put("description","正文可用，图片特征受控失败")));
        String partialRevision=partial.path("revisionId").asText();var partialArtifacts=(com.fasterxml.jackson.databind.node.ObjectNode)json.readTree(db.queryForObject("SELECT artifacts_json FROM reference_revision WHERE id=?",String.class,partialRevision));partialArtifacts.set("parts",json.readTree("{\"BODY\":{\"status\":\"AVAILABLE\"},\"OCR:image\":{\"status\":\"AVAILABLE\",\"result\":{\"ocrStatus\":\"EMPTY\",\"combinedText\":\"\"}}}"));db.update("UPDATE reference_revision SET processing_status='PREPARED',artifacts_json=? WHERE id=?",json.writeValueAsString(partialArtifacts),partialRevision);
        when(client.call(eq(false),eq("/library/build"),any(),anyString())).thenAnswer(call->{
            var request=(com.fasterxml.jackson.databind.JsonNode)call.getArgument(2);Path path=Path.of(request.path("manifestPath").asText());var input=json.readTree(Files.readString(path));String generation=input.path("generationId").asText();
            var manifest=json.createObjectNode().put("generationId",generation);manifest.set("documents",input.path("documents"));manifest.putArray("images");var enabled=manifest.putArray("enabledReferenceWorkIds");var ids=new TreeSet<String>();input.path("documents").forEach(row->ids.add(row.path("sourceWorkId").asText()));ids.forEach(enabled::add);
            Path target=path.getParent().resolve("manifest.json");Files.writeString(target,json.writeValueAsString(manifest));String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(target)));Files.writeString(path.getParent().resolve("READY"),hash);
            var response=json.createObjectNode().put("status","READY").put("generationId",generation).put("manifestSha256",hash);var parts=response.putArray("partResults");for(var image:input.path("images"))parts.addObject().put("sourceRevisionId",image.path("sourceRevisionId").asText()).put("key","IMAGE:"+image.path("nodeId").asText()).put("status","FAILED").put("errorCode","CONTROLLED_IMAGE_FAILURE");return response;
        });
        processor.refresh();
        assertEquals("FAILED",db.queryForObject("SELECT processing_status FROM reference_revision WHERE id=?",String.class,revision));
        assertEquals("PARTIAL",db.queryForObject("SELECT processing_status FROM reference_revision WHERE id=?",String.class,partialRevision));
        assertTrue(references.list(admin,1,20,partialTitle).path("items").get(0).path("effectiveEnabled").asBoolean());
    }
}
