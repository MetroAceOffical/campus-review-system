package local.campus.review.workbench;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/workbench/training")
public class TrainingController {
    private final TrainingService training;private final CurrentUserService users;
    public TrainingController(TrainingService training,CurrentUserService users){this.training=training;this.users=users;}
    @PostMapping("/runs") Api start(Authentication auth,@RequestBody TrainingService.Start request){return Api.ok(training.start(users.require(auth),request));}
    @GetMapping("/runs") Api runs(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="")String q){return Api.ok(training.runs(users.require(auth),page,q));}
    @GetMapping("/models") Api models(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="false")boolean archived){return Api.ok(training.models(users.require(auth),page,q,archived));}
    @GetMapping("/runs/{id}/samples") Api samples(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="pairs")String kind,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="10")int pageSize)throws Exception{return Api.ok(training.samples(users.require(auth),id,kind,page,pageSize));}
    public record Edit(String name,Boolean archived){}
    @PatchMapping("/models/{id}") Api edit(Authentication auth,@PathVariable String id,@RequestBody Edit request){return Api.ok(training.updateModel(users.require(auth),id,request.name(),request.archived()));}
    @GetMapping("/runs/{id}/files/{name}") ResponseEntity<FileSystemResource> artifact(Authentication auth,@PathVariable String id,@PathVariable String name){
        var path=training.artifact(users.require(auth),id,name);return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\""+name+"\"").body(new FileSystemResource(path));
    }
}
