package local.campus.review.manuscript;
import com.fasterxml.jackson.databind.JsonNode;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.*;
import local.campus.review.content.DocumentModels.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
public class SubmissionController {
    public record Submit(Long expectedDraftRevision,String title,String schemaVersion,JsonNode content,List<Source> sources){}
    private final SubmissionService submissions;private final CurrentUserService users;
    public SubmissionController(SubmissionService submissions,CurrentUserService users){this.submissions=submissions;this.users=users;}
    @PostMapping("/api/manuscripts/{id}/submissions") Api submit(Authentication auth,@PathVariable String id,@RequestHeader("Idempotency-Key")String key,@RequestBody Submit input){
        if(input.expectedDraftRevision()==null)throw new ApiException(400,"VALIDATION_ERROR","缺少草稿修订号");
        return Api.ok(submissions.submit(users.require(auth),id,key,input.expectedDraftRevision(),new DocumentInput(input.title(),input.schemaVersion(),input.content(),input.sources())));
    }
    @GetMapping("/api/submissions/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(submissions.get(users.require(auth),id));}
}
