package local.campus.review.review;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import local.campus.review.reference.PublicationService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
public class ReviewController {
    private final ReviewService reviews;private final CurrentUserService users;private final PublicationService publications;private final ReviewQueryService queries;
    public ReviewController(ReviewService reviews,CurrentUserService users,PublicationService publications,ReviewQueryService queries){this.reviews=reviews;this.users=users;this.publications=publications;this.queries=queries;}
    public record Decision(String decision,String reason,String checkId){}
    @PostMapping("/api/submissions/{id}/decision") Api decide(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Decision input){return Api.ok(reviews.decide(users.require(auth),id,key,input.decision(),input.reason(),input.checkId()));}
    @GetMapping("/api/publications/{id}") Api get(Authentication auth,@PathVariable String id){users.require(auth);return Api.ok(publications.get(id));}
    @GetMapping("/api/publications") Api published(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q){users.require(auth);return Api.ok(publications.list(page,pageSize,q));}
    @GetMapping("/api/reviews") Api list(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="PENDING")String status){return Api.ok(queries.list(users.require(auth),page,pageSize,q,status));}
}
