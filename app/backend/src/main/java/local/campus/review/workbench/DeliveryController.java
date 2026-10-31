package local.campus.review.workbench;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
@RestController @RequestMapping("/api/workbench")
public class DeliveryController {
    private final ReleaseService releases;private final ReferenceImportService imports;private final CurrentUserService users;
    public DeliveryController(ReleaseService releases,ReferenceImportService imports,CurrentUserService users){this.releases=releases;this.imports=imports;this.users=users;}
    @GetMapping("/releases")Api list(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize){return Api.ok(releases.list(users.require(a),page,pageSize));}
    @GetMapping("/releases/{id}")Api get(Authentication a,@PathVariable String id){return Api.ok(releases.get(users.require(a),id));}
    @GetMapping("/releases/history")Api history(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize){return Api.ok(releases.history(users.require(a),page,pageSize));}
    @GetMapping("/releases/text-profiles")Api profiles(Authentication a)throws Exception{return Api.ok(releases.textProfiles(users.require(a)));}
    @GetMapping("/releases/models/{id}/evaluations")Api evaluations(Authentication a,@PathVariable String id){return Api.ok(releases.evaluations(users.require(a),id));}
    @PostMapping("/releases")Api create(Authentication a,@RequestBody ReleaseService.Create input){return Api.ok(releases.create(users.require(a),input));}
    public record Switch(String expectedId){}
    @PostMapping("/releases/{id}/activate")Api activate(Authentication a,@PathVariable String id,@RequestBody Switch input){return Api.ok(releases.activate(users.require(a),id,input.expectedId()));}
    public record Prediction(String organizationId,JsonNode rows){}
    public record Reset(String organizationId,String scene,String expectedId){}
    @PostMapping("/releases/reset")Api reset(Authentication a,@RequestBody Reset input){return Api.ok(releases.reset(users.require(a),input.organizationId(),input.scene(),input.expectedId()));}
    @PostMapping("/releases/predict")Api predict(Authentication a,@RequestBody Prediction input)throws Exception{return Api.ok(releases.predict(users.require(a),input.organizationId(),input.rows()));}
    @GetMapping("/reference-imports")Api imports(Authentication a,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize){return Api.ok(imports.list(users.require(a),page,pageSize));}
    @PostMapping("/reference-imports")Api start(Authentication a,@RequestBody ReferenceImportService.Start input){return Api.ok(imports.create(users.require(a),input));}
    @GetMapping("/reference-imports/{id}")Api batch(Authentication a,@PathVariable String id){return Api.ok(imports.get(users.require(a),id));}
    @GetMapping("/reference-imports/{id}/rows")Api rows(Authentication a,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize){return Api.ok(imports.rows(users.require(a),id,page,pageSize));}
    @PostMapping("/reference-imports/{id}/{action}")Api action(Authentication a,@PathVariable String id,@PathVariable String action){return Api.ok(imports.action(users.require(a),id,action));}
}
