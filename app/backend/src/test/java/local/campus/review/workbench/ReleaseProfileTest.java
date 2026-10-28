package local.campus.review.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ReleaseProfileTest {
    private final ObjectMapper json=new ObjectMapper();

    @Test void profileMustMatchTheSelectedReferenceGeneration() throws Exception {
        var manifest=json.readTree("{\"profileId\":\"profile\",\"libraryGenerationId\":\"42\",\"libraryManifestSha256\":\"hash\"}");
        assertDoesNotThrow(()->ReleaseService.requireProfileLibrary(manifest,"42","hash"));
        assertEquals("REFERENCE_PROFILE_STALE",assertThrows(ApiException.class,()->ReleaseService.requireProfileLibrary(manifest,"43","hash")).code);
        assertEquals("REFERENCE_PROFILE_STALE",assertThrows(ApiException.class,()->ReleaseService.requireProfileLibrary(manifest,"42","changed")).code);
    }

    @Test void profileMustBeLoadedWithTheSameConfigIdentity() throws Exception {
        var manifest=json.readTree("{\"profileId\":\"profile\",\"textConfig\":{\"configId\":\"v3\"}}");
        var ready=json.readTree("{\"ready\":true,\"availableTextConfigs\":[{\"profileId\":\"profile\",\"configId\":\"v3\"}]}");
        assertDoesNotThrow(()->ReleaseService.requireProfileLoaded(manifest,ready));
        var wrong=json.readTree("{\"ready\":true,\"availableTextConfigs\":[{\"profileId\":\"other\",\"configId\":\"v3\"}]}");
        assertEquals("PROFILE_NOT_LOADED",assertThrows(ApiException.class,()->ReleaseService.requireProfileLoaded(manifest,wrong)).code);
        assertEquals("PROFILE_NOT_LOADED",assertThrows(ApiException.class,()->ReleaseService.requireProfileLoaded(manifest,json.createObjectNode())).code);
    }
}
