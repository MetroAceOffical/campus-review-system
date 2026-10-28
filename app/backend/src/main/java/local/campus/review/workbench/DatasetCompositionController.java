package local.campus.review.workbench;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.nio.file.Files;

@RestController
@RequestMapping("/api/workbench/datasets")
public class DatasetCompositionController {
    private final DatasetCompositionService compositions;private final DatasetService data;private final CurrentUserService users;
    public DatasetCompositionController(DatasetCompositionService compositions,DatasetService data,CurrentUserService users){this.compositions=compositions;this.data=data;this.users=users;}
    @PostMapping("/compose") Api create(Authentication auth,@RequestBody DatasetCompositionService.Create input)throws Exception{return Api.ok(compositions.create(users.require(auth),input));}
    @GetMapping("/{id}/versions/{version}/composition") Api report(Authentication auth,@PathVariable String id,@PathVariable String version)throws Exception{return Api.ok(data.json.readTree(Files.readString(data.download(users.require(auth),id,version,"composition.json"))));}
}
