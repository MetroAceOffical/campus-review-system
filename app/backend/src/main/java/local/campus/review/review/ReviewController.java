package local.campus.review.review;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import local.campus.review.reference.PublicationService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
public class ReviewController {
    private final ReviewService reviews;private final CurrentUserService users;private final PublicationService publications;
    public ReviewController(ReviewService reviews,CurrentUserService users,PublicationService publications){this.reviews=reviews;this.users=users;this.publications=publications;}
    public record Decision(String decision,String reason){}
    @PostMapping("/api/submissions/{id}/decision") Api decide(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Decision input){return Api.ok(reviews.decide(users.require(auth),id,key,input.decision(),input.reason()));}
    @GetMapping("/api/publications/{id}") Api get(Authentication auth,@PathVariable String id){users.require(auth);return Api.ok(publications.get(id));}
}
