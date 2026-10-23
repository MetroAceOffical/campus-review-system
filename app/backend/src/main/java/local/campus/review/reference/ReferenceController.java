package local.campus.review.reference;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/references")
public class ReferenceController {
    private final ReferenceService references;private final CurrentUserService users;
    public ReferenceController(ReferenceService references,CurrentUserService users){this.references=references;this.users=users;}
    @PostMapping Api create(Authentication auth,@RequestHeader("Idempotency-Key")String key,@RequestBody ReferenceService.ReferenceInput input){return Api.ok(references.create(users.require(auth),key,input));}
    @GetMapping Api list(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q){return Api.ok(references.list(users.require(auth),page,pageSize,q));}
    @GetMapping("/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(references.get(users.require(auth),id));}
    public record Enabled(boolean enabled){}
    public record Retry(java.util.List<String> failedPartKeys){}
    @PostMapping("/{id}/retries") Api retry(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody(required=false) Retry input){return Api.ok(references.retry(users.require(auth),id,key,input==null?null:input.failedPartKeys()));}
    @PatchMapping("/{id}/enabled") ResponseEntity<Api> enabled(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Enabled input){return ResponseEntity.accepted().body(Api.ok(references.setEnabled(users.require(auth),id,key,input.enabled())));}
}
