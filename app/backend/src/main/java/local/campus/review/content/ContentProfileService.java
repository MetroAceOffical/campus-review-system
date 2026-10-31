package local.campus.review.content;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.common.*;
import local.campus.review.detection.DetectorClient;
import local.campus.review.reference.LibraryGenerationService;
import local.campus.review.workbench.ReleaseService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
@Service
public class ContentProfileService {
    private final JdbcTemplate db;private final ObjectMapper json;private final DetectorClient detector;private final LibraryGenerationService libraries;private final ReleaseService releases;
    public ContentProfileService(JdbcTemplate db,ObjectMapper json,DetectorClient detector,LibraryGenerationService libraries,ReleaseService releases){this.db=db;this.json=json;this.detector=detector;this.libraries=libraries;this.releases=releases;}
    public ObjectNode capture(String manuscript,boolean required){
        var health=detector.health(false);String generation=libraries.currentId();
        if(!health.path("ready").asBoolean()||generation==null){if(required)throw new ApiException(503,"DETECTION_UNAVAILABLE","内容检测服务尚未就绪，请稍后重检");return null;}
        String hash=db.queryForObject("SELECT manifest_sha256 FROM library_generation WHERE id=?",String.class,generation),org=db.queryForObject("SELECT organization_id FROM manuscript WHERE id=?",String.class,manuscript);
        var selected=releases.textSelection(org,health.path("configs").path("textConfig"),generation,hash);
        selected.put("libraryGenerationId",generation).put("libraryManifestSha256",hash);selected.set("imageConfig",health.path("configs").path("imageConfig"));
        selected.put("identity",JsonSupport.hash(json,selected));return selected;
    }
}
