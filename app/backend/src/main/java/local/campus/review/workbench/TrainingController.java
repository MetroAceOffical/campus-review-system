package local.campus.review.workbench;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/workbench/training")
public class TrainingController {
    private final TrainingService training;private final CurrentUserService users;
    public TrainingController(TrainingService training,CurrentUserService users){this.training=training;this.users=users;}
    @PostMapping("/runs") Api start(Authentication auth,@RequestBody TrainingService.Start request){return Api.ok(training.start(users.require(auth),request));}
    @GetMapping("/runs") Api runs(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(required=false)String modelId){return Api.ok(training.runs(users.require(auth),page,pageSize,q,modelId));}
    @GetMapping("/models") Api models(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="false")boolean archived){return Api.ok(training.models(users.require(auth),page,pageSize,q,archived));}
    @GetMapping("/models/{id}") Api model(Authentication auth,@PathVariable String id){return Api.ok(training.getModel(users.require(auth),id));}
    @GetMapping("/runs/{id}/samples") Api samples(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="pairs")String kind,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="10")int pageSize)throws Exception{return Api.ok(training.samples(users.require(auth),id,kind,page,pageSize));}
    @GetMapping("/runs/{id}/predictions") Api predictions(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(required=false)Integer predicted,@RequestParam(defaultValue="all")String outcome)throws Exception{return Api.ok(training.predictions(users.require(auth),id,page,pageSize,q,predicted,outcome));}
    @PostMapping(value="/models/{id}/predict-file",consumes=MediaType.MULTIPART_FORM_DATA_VALUE) Api predictFile(Authentication auth,@PathVariable String id,@RequestParam MultipartFile file)throws Exception{return Api.ok(training.predictFile(users.require(auth),id,file));}
    public record Edit(String name,Boolean archived){}
    @PatchMapping("/models/{id}") Api edit(Authentication auth,@PathVariable String id,@RequestBody Edit request){return Api.ok(training.updateModel(users.require(auth),id,request.name(),request.archived()));}
    @GetMapping("/runs/{id}/files/{name}") ResponseEntity<FileSystemResource> artifact(Authentication auth,@PathVariable String id,@PathVariable String name){
        var path=training.artifact(users.require(auth),id,name);return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\""+name+"\"").body(new FileSystemResource(path));
    }
}
