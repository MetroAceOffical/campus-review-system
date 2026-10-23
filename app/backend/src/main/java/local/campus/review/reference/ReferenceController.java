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
    @GetMapping Api list(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize){return Api.ok(references.list(users.require(auth),page,pageSize));}
    public record Enabled(boolean enabled){}
    @PatchMapping("/{id}/enabled") ResponseEntity<Api> enabled(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Enabled input){return ResponseEntity.accepted().body(Api.ok(references.setEnabled(users.require(auth),id,key,input.enabled())));}
}
