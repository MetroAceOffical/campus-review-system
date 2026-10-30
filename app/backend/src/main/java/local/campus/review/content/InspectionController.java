package local.campus.review.content;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController
public class InspectionController {
    private final InspectionService checks;private final CurrentUserService users;private final JdbcTemplate db;
    public InspectionController(InspectionService checks,CurrentUserService users,JdbcTemplate db){this.checks=checks;this.users=users;this.db=db;}
    public record Start(String kind,DocumentModels.DocumentInput document){}
    @PostMapping("/api/manuscripts/{id}/checks") Api draft(Authentication auth,@PathVariable String id,@RequestBody Start input)throws Exception{return Api.ok(checks.draft(users.require(auth),id,input.kind(),input.document()));}
    @GetMapping("/api/manuscripts/{id}/checks") Api draftList(Authentication auth,@PathVariable String id){return Api.ok(checks.list(users.require(auth),id,null));}
    @GetMapping("/api/manuscripts/{id}/checks/history") Api draftHistory(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String panel){return Api.ok(checks.history(users.require(auth),id,null,page,pageSize,panel));}
    @PostMapping("/api/submissions/{id}/checks") Api submission(Authentication auth,@PathVariable String id,@RequestBody Start input)throws Exception{return Api.ok(checks.submission(users.require(auth),id,input.kind()));}
    @GetMapping("/api/submissions/{id}/checks") Api submissionList(Authentication auth,@PathVariable String id){var rows=db.queryForList("SELECT manuscript_id FROM submission_version WHERE id=?",id);if(rows.isEmpty())throw new local.campus.review.common.ApiException(404,"RESOURCE_NOT_FOUND","未找到可访问的送审版本");return Api.ok(checks.list(users.require(auth),rows.getFirst().get("manuscript_id").toString(),id));}
    @GetMapping("/api/submissions/{id}/checks/history") Api submissionHistory(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String panel){var rows=db.queryForList("SELECT manuscript_id FROM submission_version WHERE id=?",id);if(rows.isEmpty())throw new local.campus.review.common.ApiException(404,"RESOURCE_NOT_FOUND","未找到可访问的送审版本");return Api.ok(checks.history(users.require(auth),rows.getFirst().get("manuscript_id").toString(),id,page,pageSize,panel));}
    @GetMapping("/api/document-checks/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(checks.get(users.require(auth),id));}
    @GetMapping("/api/document-checks/{id}/events") Api events(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="0")long after){return Api.ok(checks.events(users.require(auth),id,after));}
    @PostMapping("/api/document-checks/{id}/cancel") Api cancel(Authentication auth,@PathVariable String id){return Api.ok(checks.cancel(users.require(auth),id));}
    public record Feedback(String issueId,String action){}
    @PostMapping("/api/document-checks/{id}/feedback") Api feedback(Authentication auth,@PathVariable String id,@RequestBody Feedback input){return Api.ok(checks.feedback(users.require(auth),id,input.issueId(),input.action()));}
}
