package local.campus.review.content;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController
public class EvidenceSourceController {
    private final EvidenceSourceService sources;private final CurrentUserService users;
    public EvidenceSourceController(EvidenceSourceService sources,CurrentUserService users){this.sources=sources;this.users=users;}
    @GetMapping("/api/evidence-source") Api get(Authentication a,@RequestParam(required=false)String batch,@RequestParam(required=false)String check,@RequestParam String evidence){return Api.ok(sources.get(users.require(a),batch,check,evidence));}
}
