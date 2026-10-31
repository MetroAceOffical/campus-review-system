package local.campus.review.workbench;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/workbench/flows")
public class WorkbenchFlowController {
    final WorkbenchFlowService flows;final CurrentUserService users;
    public WorkbenchFlowController(WorkbenchFlowService flows,CurrentUserService users){this.flows=flows;this.users=users;}
    @PostMapping Api create(Authentication a,@RequestBody WorkbenchFlowService.Create input){return Api.ok(flows.create(users.require(a),input));}
    @GetMapping Api list(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="12")int pageSize,@RequestParam(defaultValue="")String q){return Api.ok(flows.list(users.require(a),page,pageSize,q));}
    @GetMapping("/{id}") Api get(Authentication a,@PathVariable String id){return Api.ok(flows.get(users.require(a),id));}
    @PatchMapping("/{id}") Api update(Authentication a,@PathVariable String id,@RequestBody WorkbenchFlowService.Edit input){return Api.ok(flows.update(users.require(a),id,input));}
}
