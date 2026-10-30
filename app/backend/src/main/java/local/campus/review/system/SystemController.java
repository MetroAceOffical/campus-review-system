package local.campus.review.system;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/system")
public class SystemController {
    private final SystemService system;private final CurrentUserService users;
    public SystemController(SystemService system,CurrentUserService users){this.system=system;this.users=users;}
    @GetMapping("/users") Api users(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="")String role,@RequestParam(defaultValue="")String enabled){return Api.ok(system.users(users.require(a),page,pageSize,q,role,enabled));}
    @PostMapping("/users") Api createUser(Authentication a,@RequestBody SystemService.UserInput input){return Api.ok(system.saveUser(users.require(a),null,input));}
    @PutMapping("/users/{id}") Api updateUser(Authentication a,@PathVariable String id,@RequestBody SystemService.UserInput input){return Api.ok(system.saveUser(users.require(a),id,input));}
    @GetMapping("/organizations") Api organizations(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q){return Api.ok(system.organizations(users.require(a),page,pageSize,q));}
    @GetMapping("/organization-options") Api options(Authentication a){return Api.ok(system.organizationOptions(users.require(a)));}
    @PostMapping("/organizations") Api createOrganization(Authentication a,@RequestBody SystemService.OrganizationInput input){return Api.ok(system.saveOrganization(users.require(a),null,input));}
    @PutMapping("/organizations/{id}") Api updateOrganization(Authentication a,@PathVariable String id,@RequestBody SystemService.OrganizationInput input){return Api.ok(system.saveOrganization(users.require(a),id,input));}
    @GetMapping("/logs") Api logs(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q){return Api.ok(system.logs(users.require(a),page,pageSize,q));}
    @GetMapping("/tasks") Api tasks(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="")String status){return Api.ok(system.tasks(users.require(a),page,pageSize,q,status));}
    @GetMapping("/diagnostics") Api diagnostics(Authentication a){return Api.ok(system.diagnostics(users.require(a)));}
}
