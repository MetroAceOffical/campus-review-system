package local.campus.review.experiment;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class ExperimentCatalogTest {
    @Test void corruptReplacementKeepsLastVerifiedPackage()throws Exception{
        Path source=Path.of(System.getenv("CAMPUS_ROOT"),"runtime/experiments"),target=Files.createTempDirectory(Path.of(System.getenv("CAMPUS_ROOT"),"runtime/test-tmp"),"catalog-");
        try{
            try(var paths=Files.walk(source)){for(Path path:paths.toList()){Path dest=target.resolve(source.relativize(path));if(Files.isDirectory(path))Files.createDirectories(dest);else Files.copy(path,dest);}}
            var json=new ObjectMapper();var catalog=new ExperimentCatalog(target,json);
            var first=catalog.list();String version=first.path("experiments").get(0).path("contentVersion").asText();
            var index=json.readTree(Files.readString(target.resolve("catalog.json")));Path manifestPath=target.resolve(index.path("experiments").get(0).path("manifest").asText());
            var manifest=(com.fasterxml.jackson.databind.node.ObjectNode)json.readTree(Files.readString(manifestPath));manifest.put("contentVersion","controlled-test-new-version");Files.writeString(manifestPath,json.writeValueAsString(manifest));
            String hash=java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(manifestPath)));Files.writeString(manifestPath.getParent().resolve("READY"),hash);((com.fasterxml.jackson.databind.node.ObjectNode)index.path("experiments").get(0)).put("manifestSha256",hash);Files.writeString(target.resolve("catalog.json"),json.writeValueAsString(index));
            assertEquals("controlled-test-new-version",catalog.list().path("experiments").get(0).path("contentVersion").asText());version="controlled-test-new-version";
            Path metrics=manifestPath.getParent().resolve("metrics.json");byte[] original=Files.readAllBytes(metrics);Files.writeString(metrics,"{}");assertTrue(catalog.list().hasNonNull("warning"));assertEquals(1975,catalog.bundle("pawsx-zh-round2").path("metrics").path("sets").path("official_test").path("n").asInt());Files.write(metrics,original);
            Files.writeString(target.resolve("catalog.json"),"{broken");
            var fallback=catalog.list();assertEquals(version,fallback.path("experiments").get(0).path("contentVersion").asText());assertTrue(fallback.hasNonNull("warning"));
            assertThrows(local.campus.review.common.ApiException.class,()->new ExperimentCatalog(target,new ObjectMapper()).list());
        }finally{try(var paths=Files.walk(target)){for(var path:paths.sorted(java.util.Comparator.reverseOrder()).toList())Files.delete(path);}}
    }
}
