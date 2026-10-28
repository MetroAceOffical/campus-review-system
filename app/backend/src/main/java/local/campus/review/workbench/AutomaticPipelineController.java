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
    @GetMapping Api list(Authentication auth,@RequestParam String datasetId,@RequestParam(defaultValue="1")int page){return Api.ok(pipelines.list(users.require(auth),datasetId,page));}
    @GetMapping("/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(pipelines.get(users.require(auth),id));}
    @PostMapping("/{id}/cancel") Api cancel(Authentication auth,@PathVariable String id){return Api.ok(pipelines.control(users.require(auth),id,false));}
    @PostMapping("/{id}/retry") Api retry(Authentication auth,@PathVariable String id){return Api.ok(pipelines.control(users.require(auth),id,true));}
}
