package local.campus.review.manuscript;

import com.fasterxml.jackson.databind.JsonNode;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.*;
import local.campus.review.content.DocumentModels.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/manuscripts")
public class DraftController {
    private final DraftService drafts;
    private final CurrentUserService users;
    public DraftController(DraftService drafts,CurrentUserService users){this.drafts=drafts;this.users=users;}
    public record Create(String organizationId,String title) {}
    public record Save(Long expectedRevision,String title,String schemaVersion,JsonNode content,List<Source> sources) {}
    @PostMapping Api create(Authentication authentication,@RequestBody Create input){return Api.ok(drafts.create(users.require(authentication),input.organizationId(),input.title()));}
    @GetMapping("/{id}/draft") Api get(Authentication authentication,@PathVariable String id){return Api.ok(drafts.get(users.require(authentication),id));}
    @PutMapping("/{id}/draft") Api save(Authentication authentication,@PathVariable String id,@RequestBody Save input) {
        if(input.expectedRevision()==null || input.expectedRevision()<0)throw new ApiException(400,"VALIDATION_ERROR","缺少有效的草稿修订号");
        return Api.ok(drafts.save(users.require(authentication),id,input.expectedRevision(),new DocumentInput(input.title(),input.schemaVersion(),input.content(),input.sources())));
    }
}
