package local.campus.review.reference;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.RuntimeSettings;
import local.campus.review.detection.DetectorClient;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;
import java.nio.file.Files;
import java.security.MessageDigest;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;

class AdaptiveOcrIT {
    @Test void actualAdaptiveServiceAndCacheKeepConfigurationAndAttemptIdentity() throws Exception {
        Assumptions.assumeTrue("1".equals(System.getenv("CAMPUS_OCR_INTEGRATION")));
        var json=new ObjectMapper();var settings=new RuntimeSettings(json);var client=new DetectorClient(settings,json);
        var config=client.frozenOcrConfig();assertEquals("ocr-v2",config.path("schemaVersion").asText());
        var health=client.health(true);assertTrue(health.path("ready").asBoolean());assertNotEquals(config,health.path("config"));
        var path=settings.root().resolve("runtime/probes/vision-stage18-20261028/ocr-large.img");
        var input=json.createObjectNode().put("taskId","stage18-java").put("attemptId","first").put("fileId","stage18-java-image").put("path",path.toString()).put("fileSha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))));
        var processor=new ReferenceProcessor(null,json,settings,client,null);var first=processor.recognize(input,config,health);
        assertEquals(config,first.path("actualConfig"));assertTrue(first.path("fallbackUsed").asBoolean());
        input.put("attemptId","second");var second=processor.recognize(input,config,health);
        assertTrue(second.path("recognitionCacheHit").asBoolean());assertEquals("second",second.path("attemptId").asText());assertEquals(config,second.path("actualConfig"));
        assertEquals(first.path("recognitionLines"),second.path("recognitionLines"));
    }
}
