package local.campus.review.workbench;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/workbench/training")
public class ModelComparisonController {
    private final ModelComparisonService comparisons;private final CurrentUserService users;
    public ModelComparisonController(ModelComparisonService comparisons,CurrentUserService users){this.comparisons=comparisons;this.users=users;}
    @PostMapping("/models/{id}/compare-parent") Api create(Authentication a,@PathVariable String id,@RequestBody ModelComparisonService.Start input){return Api.ok(comparisons.create(users.require(a),id,input));}
    @GetMapping("/models/{id}/comparisons") Api list(Authentication a,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="10")int pageSize){return Api.ok(comparisons.list(users.require(a),id,page,pageSize));}
    @GetMapping("/comparisons/{id}") Api get(Authentication a,@PathVariable String id){return Api.ok(comparisons.get(users.require(a),id));}
    @GetMapping("/comparisons/{id}/changes") Api changes(Authentication a,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="10")int pageSize,@RequestParam(defaultValue="errors")String filter)throws Exception{return Api.ok(comparisons.changes(users.require(a),id,page,pageSize,filter));}
}
