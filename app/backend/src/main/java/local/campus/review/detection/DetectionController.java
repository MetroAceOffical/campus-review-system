package local.campus.review.detection;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
public class DetectionController {
    private final DetectionRetryService retries;private final CurrentUserService users;
    public DetectionController(DetectionRetryService retries,CurrentUserService users){this.retries=retries;this.users=users;}
    public record Retry(String expectedAttemptId){}
    @PostMapping("/api/detection-items/{id}/retries") Api retry(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Retry input){return Api.ok(retries.retry(users.require(auth),id,key,input.expectedAttemptId()));}
}
