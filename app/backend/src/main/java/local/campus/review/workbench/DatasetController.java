package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/workbench")
public class DatasetController {
    private final DatasetService datasets;private final CurrentUserService users;
    public DatasetController(DatasetService datasets,CurrentUserService users){this.datasets=datasets;this.users=users;}
    @GetMapping("/organizations") Api organizations(Authentication auth){return Api.ok(datasets.organizations(users.require(auth)));}
    @GetMapping("/datasets") Api list(Authentication auth,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize,@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="false")boolean archived){return Api.ok(datasets.list(users.require(auth),page,pageSize,q,archived));}
    @PostMapping("/datasets") Api upload(Authentication auth,@RequestParam String organizationId,@RequestParam String name,@RequestParam String kind,@RequestParam MultipartFile file,@RequestParam(required=false) String purpose)throws Exception{return Api.ok(datasets.upload(users.require(auth),organizationId,name,kind,file,purpose));}
    @GetMapping("/datasets/{id}") Api get(Authentication auth,@PathVariable String id){return Api.ok(datasets.get(users.require(auth),id));}
    public record Edit(String name,Boolean archived,String purpose){}
    @PatchMapping("/datasets/{id}") Api edit(Authentication auth,@PathVariable String id,@RequestBody Edit edit){return Api.ok(datasets.update(users.require(auth),id,edit.name(),edit.archived(),edit.purpose()));}
    public record Run(String versionId,String action,JsonNode mapping,JsonNode options){}
    @GetMapping("/datasets/{id}/runs") Api runs(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize){return Api.ok(datasets.runs(users.require(auth),id,page,pageSize));}
    @PostMapping("/datasets/{id}/runs") Api start(Authentication auth,@PathVariable String id,@RequestBody Run run){return Api.ok(datasets.start(users.require(auth),id,run.versionId(),run.action(),run.mapping(),run.options()));}
    @GetMapping("/runs/{id}") Api run(Authentication auth,@PathVariable String id){return Api.ok(datasets.run(users.require(auth),id));}
    @GetMapping("/runs/{id}/events") Api events(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="0")long after){return Api.ok(datasets.events(users.require(auth),id,after));}
    @PostMapping("/runs/{id}/cancel") Api cancel(Authentication auth,@PathVariable String id){return Api.ok(datasets.cancel(users.require(auth),id));}
    @GetMapping("/datasets/{id}/versions/{version}/rows") Api rows(Authentication auth,@PathVariable String id,@PathVariable String version,@RequestParam(defaultValue="1")int page,@RequestParam(defaultValue="20")int pageSize)throws Exception{return Api.ok(datasets.rows(users.require(auth),id,version,page,pageSize));}
    @GetMapping("/datasets/{id}/versions/{version}/report") Api report(Authentication auth,@PathVariable String id,@PathVariable String version)throws Exception{return Api.ok(datasets.json.readTree(java.nio.file.Files.readString(datasets.download(users.require(auth),id,version,"cleaning.json"))));}
    @GetMapping("/datasets/{id}/versions/{version}/files/{artifact}") ResponseEntity<FileSystemResource> download(Authentication auth,@PathVariable String id,@PathVariable String version,@PathVariable String artifact){
        var file=datasets.download(users.require(auth),id,version,artifact);return ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\""+file.getFileName()+"\"").body(new FileSystemResource(file));
    }
}
