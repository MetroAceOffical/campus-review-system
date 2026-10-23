package local.campus.review.detection;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.CurrentUser;
import local.campus.review.content.FileService;
import local.campus.review.reference.*;
import local.campus.review.common.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@EnabledIfEnvironmentVariable(named="CAMPUS_REAL_MODELS",matches="1")
@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
class RealPipelineIT {
    @Autowired JdbcTemplate db;@Autowired ObjectMapper json;@Autowired RuntimeSettings settings;
    @Autowired FileService files;@Autowired ReferenceService references;@Autowired JobWorker worker;
    @Autowired DetectorClient client;@Autowired DetectionService detection;
    @Test void javaToBothPythonServicesAndDatabase()throws Exception{
        assertTrue(client.health(false).path("ready").asBoolean(),"Dedicated test detector must be ready");
        assertTrue(client.health(true).path("ready").asBoolean(),"OCR must be ready");
        assertEquals("campus_review_midterm_test",db.queryForObject("SELECT DATABASE()",String.class));
        db.update("UPDATE background_job SET status='INTERRUPTED',error_code='TEST_FIXTURE_RESET' WHERE status IN ('QUEUED','WAITING_SERVICE','RUNNING')");
        String adminId=db.queryForObject("SELECT id FROM app_user WHERE username='admin'",String.class);
        var admin=new CurrentUser(adminId,"test admin",CurrentUser.Role.ADMIN,Set.of(),List.of());
        var bytes=Files.readAllBytes(settings.root().resolve("validation/remaining/vision/inputs/mixed-known.png"));
        var upload=files.upload(admin,new MockMultipartFile("file","M07-real-probe.png","image/png",bytes));
        String text="南京传媒学院校园新闻，人工审核保留原始内容与来源。".repeat(12);
        var document=json.createObjectNode().put("type","doc");var nodes=document.putArray("content");
        nodes.addObject().put("type","paragraph").putObject("attrs").put("nodeId","p");
        ((com.fasterxml.jackson.databind.node.ObjectNode)nodes.get(0)).putArray("content").addObject().put("type","text").put("text",text);
        nodes.addObject().put("type","campusImage").putObject("attrs").put("nodeId","image").put("fileId",upload.fileId()).put("caption","M07测试").put("origin","CITED").put("sourceUrl","https://example.org/m07-fixture");
        var created=references.create(admin,UUID.randomUUID().toString(),new ReferenceService.ReferenceInput("M07隔离测试参考","1",document,List.of(),json.createObjectNode().put("sourceType","MANUAL").put("description","明确测试材料，不进入业务库")));
        assertEquals("COMPLETED",worker.runOne().status());
        assertEquals("COMPLETED",worker.runOne().status());
        var query=document.deepCopy();var queryNodes=(com.fasterxml.jackson.databind.node.ArrayNode)query.path("content");
        for(int i=1;i<6;i++){
            var extra=nodes.get(1).deepCopy();((com.fasterxml.jackson.databind.node.ObjectNode)extra.path("attrs")).put("nodeId","image-"+i);queryNodes.add(extra);
        }
        String version=DetectionFixtures.version(db,json.writeValueAsString(query));
        db.update("UPDATE submission_version SET plain_text=? WHERE id=?",text,version);
        db.update("INSERT INTO file_binding(file_id,submission_version_id,node_id,purpose) VALUES(?,?,'image','BODY_IMAGE')",upload.fileId(),version);
        for(int i=1;i<6;i++)db.update("INSERT INTO file_binding(file_id,submission_version_id,node_id,purpose) VALUES(?,?,?,'BODY_IMAGE')",upload.fileId(),version,"image-"+i);
        String batch=detection.createFormalBatch(version,"a".repeat(64));
        assertEquals("COMPLETED",worker.runOne().status());
        assertEquals("COMPLETED",db.queryForObject("SELECT status FROM detection_batch WHERE id=?",String.class,batch));
        var results=db.queryForList("SELECT i.type,a.status,a.result_json FROM detection_item i JOIN detection_attempt a ON a.id=i.active_attempt_id WHERE i.batch_id=? ORDER BY i.id",batch);
        assertEquals(13,results.size());
        for(var row:results)assertEquals("COMPLETED",row.get("status"));
        var image=json.readTree(results.get(1).get("result_json").toString());
        assertTrue(image.path("evidence").get(0).path("similarity").asDouble()>.99);
        var ocr=json.readTree(results.get(2).get("result_json").toString());
        assertTrue(ocr.path("recognitionLines").size()>0);assertEquals("COMPLETED",ocr.path("textSearchStatus").asText());
        var evidence=json.createObjectNode().put("stage","M07").put("scope","real Java worker to both Python processes and isolated test database").put("items",13).put("allCompleted",true).put("imageSelfSimilarityAbove099",true).put("ocrLines",ocr.path("recognitionLines").size()).put("ocrTextSearchCompleted",true).put("referenceRevisionId",created.path("revisionId").asText());
        Files.writeString(settings.root().resolve("docs/midterm/evidence/M07-real-pipeline.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(evidence));
    }
}
