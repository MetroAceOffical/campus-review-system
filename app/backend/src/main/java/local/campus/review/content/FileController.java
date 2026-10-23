package local.campus.review.content;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.Api;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/files")
public class FileController {
    private final FileService files;
    private final CurrentUserService users;
    public FileController(FileService files,CurrentUserService users){this.files=files;this.users=users;}
    @PostMapping Api upload(Authentication authentication,@RequestParam("file") MultipartFile file) throws Exception {return Api.ok(files.upload(users.require(authentication),file));}
    @GetMapping("/{id}") ResponseEntity<FileSystemResource> read(Authentication authentication,@PathVariable String id) {
        var file=files.read(users.require(authentication),id);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).contentType(MediaType.parseMediaType(file.mimeType())).contentLength(file.sizeBytes()).body(new FileSystemResource(file.path()));
    }
}
