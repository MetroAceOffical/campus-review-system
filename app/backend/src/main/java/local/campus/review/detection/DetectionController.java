package local.campus.review.detection;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
public class DetectionController {
    private final DetectionRetryService retries;private final CurrentUserService users;private final DetectionQueryService queries;
    public DetectionController(DetectionRetryService retries,CurrentUserService users,DetectionQueryService queries){this.retries=retries;this.users=users;this.queries=queries;}
    public record Retry(String expectedAttemptId){}
    @PostMapping("/api/detection-items/{id}/retries") Api retry(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Retry input){return Api.ok(retries.retry(users.require(auth),id,key,input.expectedAttemptId()));}
    @GetMapping("/api/detection-batches/{id}/progress") Api progress(Authentication auth,@PathVariable String id){return Api.ok(queries.progress(users.require(auth),id));}
    @GetMapping("/api/detection-batches/{id}/report") Api report(Authentication auth,@PathVariable String id){return Api.ok(queries.report(users.require(auth),id));}
}
