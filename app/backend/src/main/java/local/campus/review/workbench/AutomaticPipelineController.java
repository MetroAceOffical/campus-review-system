package local.campus.review.workbench;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/workbench/pipelines")
public class AutomaticPipelineController {
    private final AutomaticPipelineService pipelines;private final CurrentUserService users;
    public AutomaticPipelineController(AutomaticPipelineService pipelines,CurrentUserService users){this.pipelines=pipelines;this.users=users;}
    @PostMapping Api create(Authentication auth,@RequestBody AutomaticPipelineService.Create input){return Api.ok(pipelines.create(users.require(auth),input));}
    @GetMapping Api list(Authentication auth,@RequestParam String datasetId,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="10")int pageSize){return Api.ok(pipelines.list(users.require(auth),datasetId,page,pageSize));}
    @GetMapping("/bundles") Api bundles(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="12")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="false")boolean history){return Api.ok(pipelines.bundles(users.require(auth),page,pageSize,q,history));}
    @GetMapping("/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(pipelines.get(users.require(auth),id));}
    @PostMapping("/{id}/cancel") Api cancel(Authentication auth,@PathVariable String id){return Api.ok(pipelines.control(users.require(auth),id,false));}
    @PostMapping("/{id}/retry") Api retry(Authentication auth,@PathVariable String id){return Api.ok(pipelines.control(users.require(auth),id,true));}
}
