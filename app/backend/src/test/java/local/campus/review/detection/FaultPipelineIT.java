package local.campus.review.detection;

import com.fasterxml.jackson.databind.*;
import local.campus.review.common.*;
import local.campus.review.reference.LibraryGenerationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
class FaultPipelineIT {
    @Autowired JdbcTemplate db;@Autowired ObjectMapper json;@Autowired DetectionService detection;
    @Autowired JobWorker worker;@Autowired LibraryGenerationService libraries;@Autowired RuntimeSettings settings;
    @Autowired DetectionRetryService retries;
    @MockitoBean DetectorClient client;
    @Test void unavailableWaitsAndOcrFailureKeepsOtherItemsAndPinnedPipeline()throws Exception{
        assertEquals("campus_review_midterm_test",db.queryForObject("SELECT DATABASE()",String.class));
        db.update("UPDATE background_job SET status='INTERRUPTED' WHERE status IN ('QUEUED','WAITING_SERVICE','RUNNING')");
        String generation=libraries.reserve();var directory=settings.runtime().resolve("indexes").resolve(generation);Files.createDirectories(directory);
        String manifest="{\"generationId\":\""+generation+"\",\"documents\":[],\"images\":[],\"enabledReferenceWorkIds\":[]}";
        Files.writeString(directory.resolve("manifest.json"),manifest);String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(manifest.getBytes(java.nio.charset.StandardCharsets.UTF_8)));Files.writeString(directory.resolve("READY"),hash);libraries.markReady(generation,hash);libraries.activate(generation,libraries.currentId());
        String version=DetectionFixtures.version(db,"{\"type\":\"doc\",\"content\":[{\"type\":\"campusImage\",\"attrs\":{\"nodeId\":\"image\",\"fileId\":\"1\"}}]}");
        long user=db.queryForObject("SELECT id FROM app_user WHERE username='member1'",Long.class);
        long file=SqlSupport.insert(db,"INSERT INTO stored_file(uploaded_by,storage_key,original_name,sha256,mime_type,size_bytes,width,height,created_at) VALUES(?,?,?,?,'image/png',1,1,1,UTC_TIMESTAMP(3))",user,UUID.randomUUID()+".png","fault-fixture",UUID.randomUUID().toString().replace("-","").repeat(2));
        db.update("INSERT INTO file_binding(file_id,submission_version_id,node_id,purpose) VALUES(?,?,'image','BODY_IMAGE')",file,version);
        String batch=detection.createFormalBatch(version,"a".repeat(64));
        when(client.health(false)).thenReturn(json.createObjectNode().put("ready",false));when(client.health(true)).thenReturn(json.createObjectNode().put("ready",false));
        assertEquals("WAITING_SERVICE",worker.runOne().status());
        assertEquals("WAITING_SERVICE",db.queryForObject("SELECT status FROM detection_batch WHERE id=?",String.class,batch));
        assertEquals(0,db.queryForObject("SELECT COUNT(*) FROM detection_attempt a JOIN detection_item i ON i.id=a.item_id WHERE i.batch_id=?",Integer.class,batch));
        var main=json.createObjectNode().put("ready",true);main.withObject("configs").putObject("textConfig").put("configId","frozen-text");main.withObject("configs").putObject("imageConfig").put("configId","frozen-image");when(client.health(false)).thenReturn(main);
        when(client.frozenOcrConfig()).thenReturn(json.createObjectNode().put("configId","fault-test-ocr"));
        when(client.call(eq(false),anyString(),any(),anyString())).thenAnswer(call->{var result=((com.fasterxml.jackson.databind.node.ObjectNode)call.getArgument(2)).deepCopy();return result.put("status","COMPLETED");});
        assertEquals("COMPLETED",worker.runOne().status());
        assertEquals("PARTIAL_FAILED",db.queryForObject("SELECT status FROM detection_batch WHERE id=?",String.class,batch));
        assertEquals(2,db.queryForObject("SELECT COUNT(*) FROM detection_item WHERE batch_id=? AND status='COMPLETED'",Integer.class,batch));
        assertEquals("OCR_SERVICE_UNAVAILABLE",db.queryForObject("SELECT a.error_code FROM detection_attempt a JOIN detection_item i ON i.active_attempt_id=a.id WHERE i.batch_id=? AND i.type='OCR_AND_TEXT'",String.class,batch));
        var pinned=json.readTree(db.queryForObject("SELECT pipeline_manifest_json FROM detection_batch WHERE id=?",String.class,batch));
        assertEquals(pinned,detection.pin(batch,generation,json.createObjectNode().put("changed",true)));
        assertEquals(generation,pinned.path("libraryGenerationId").asText());
        var before=db.queryForList("SELECT id,active_attempt_id FROM detection_item WHERE batch_id=? AND type<>'OCR_AND_TEXT' ORDER BY id",batch);
        var failed=db.queryForMap("SELECT * FROM detection_item WHERE batch_id=? AND type='OCR_AND_TEXT'",batch);
        var reviewer=new local.campus.review.auth.CurrentUser(db.queryForObject("SELECT id FROM app_user WHERE username='reviewer'",String.class),"reviewer",local.campus.review.auth.CurrentUser.Role.REVIEWER,Set.of(),List.of());
        retries.retry(reviewer,failed.get("id").toString(),UUID.randomUUID().toString(),failed.get("active_attempt_id").toString());
        var availableOcr=json.createObjectNode().put("ready",true);availableOcr.putObject("config").put("configId","fault-test-ocr");when(client.health(true)).thenReturn(availableOcr);
        when(client.call(eq(true),eq("/recognize"),any(),anyString())).thenAnswer(call->{var value=((com.fasterxml.jackson.databind.node.ObjectNode)call.getArgument(2)).deepCopy();value.putObject("actualConfig").put("configId","fault-test-ocr");value.put("ocrStatus","EMPTY").put("combinedText","").put("textSearchStatus","NOT_RUN");value.putArray("recognitionLines");return value;});
        assertEquals("COMPLETED",worker.runOne().status());
        assertEquals(before,db.queryForList("SELECT id,active_attempt_id FROM detection_item WHERE batch_id=? AND type<>'OCR_AND_TEXT' ORDER BY id",batch));
        assertEquals("COMPLETED",db.queryForObject("SELECT status FROM detection_batch WHERE id=?",String.class,batch));
        String timedVersion=DetectionFixtures.version(db,"{\"type\":\"doc\",\"content\":[{\"type\":\"campusImage\",\"attrs\":{\"nodeId\":\"image\",\"fileId\":\"1\"}}]}");
        db.update("INSERT INTO file_binding(file_id,submission_version_id,node_id,purpose) VALUES(?,?,'image','BODY_IMAGE')",file,timedVersion);
        String timedBatch=detection.createFormalBatch(timedVersion,"a".repeat(64));
        when(client.call(eq(false),eq("/detect/text"),any(),anyString())).thenThrow(new DetectorClient.DetectorFailure("DETECTOR_TIMEOUT"));
        assertEquals("WAITING_SERVICE",worker.runOne().status());
        assertEquals(2,db.queryForObject("SELECT COUNT(*) FROM detection_item WHERE batch_id=? AND status='QUEUED'",Integer.class,timedBatch));
        main.put("busy",true);assertEquals("WAITING_SERVICE",worker.runOne().status());
        assertEquals(1,db.queryForObject("SELECT COUNT(*) FROM detection_attempt a JOIN detection_item i ON i.id=a.item_id WHERE i.batch_id=?",Integer.class,timedBatch));
        main.put("busy",false);assertEquals("COMPLETED",worker.runOne().status());
    }
}
