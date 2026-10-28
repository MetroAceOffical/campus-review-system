package local.campus.review.content;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/citation-sources")
public class CitationController {
    private final CitationService citations;private final CurrentUserService users;
    public CitationController(CitationService citations,CurrentUserService users){this.citations=citations;this.users=users;}
    @GetMapping Api search(Authentication auth,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="")String department,@RequestParam(defaultValue="1")int page){return Api.ok(citations.search(users.require(auth),q,department,page));}
    @GetMapping("/departments") Api departments(Authentication auth){users.require(auth);return Api.ok(citations.departments());}
    @GetMapping("/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(citations.get(users.require(auth),id));}
}
