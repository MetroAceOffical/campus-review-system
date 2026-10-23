package local.campus.review.content;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import java.nio.file.*;
import java.io.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

@Service
public class FileService {
    public record UploadedFile(String fileId,String mimeType,int width,int height,long sizeBytes) {}
    public record ReadableFile(Path path,String mimeType,long sizeBytes) {}
    private final JdbcTemplate db;
    private final RuntimeSettings settings;
    private final ObjectMapper json;
    public FileService(JdbcTemplate db,RuntimeSettings settings,ObjectMapper json){this.db=db;this.settings=settings;this.json=json;}
    public UploadedFile upload(CurrentUser user,MultipartFile upload) throws Exception {
        if(user.role()!=CurrentUser.Role.MEMBER && user.role()!=CurrentUser.Role.ADMIN)throw new ApiException(403,"ACCESS_DENIED","无权上传文件");
        long limit=settings.limit("imageBytes");
        if(upload.isEmpty())throw new ApiException(400,"VALIDATION_ERROR","请选择有效图片");
        if(upload.getSize()>limit)throw new ApiException(413,"UPLOAD_TOO_LARGE","单图不能超过10MiB");
        var uploads=settings.runtime().resolve("uploads");Files.createDirectories(uploads);
        var temporary=Files.createTempFile(uploads,"upload-",".tmp");
        Path saved=null;
        try {
            var digest=MessageDigest.getInstance("SHA-256");long size=0;
            try(var input=upload.getInputStream();var output=Files.newOutputStream(temporary)) {
                byte[] buffer=new byte[65536];int count;
                while((count=input.read(buffer))!=-1) {size+=count;if(size>limit)throw new ApiException(413,"UPLOAD_TOO_LARGE","单图不能超过10MiB");output.write(buffer,0,count);digest.update(buffer,0,count);}
            }
            var process=new ProcessBuilder(settings.python().toString(),"-B",settings.root().resolve("app/scripts/inspect_image.py").toString(),temporary.toString(),Long.toString(limit),Integer.toString(settings.limit("imagePixels")),Integer.toString(settings.limit("imageSide"))).redirectError(ProcessBuilder.Redirect.DISCARD).start();
            if(!process.waitFor(60,TimeUnit.SECONDS)) {process.destroyForcibly();throw new ApiException(503,"IMAGE_VALIDATION_UNAVAILABLE","图片校验超时，请稍后重试");}
            var metadata=json.readTree(process.getInputStream().readAllBytes());
            if(metadata==null)throw new ApiException(503,"IMAGE_VALIDATION_UNAVAILABLE","图片校验服务不可用");
            if(process.exitValue()!=0) {
                String code=metadata.path("error").asText();
                throw new ApiException(Set.of("UPLOAD_TOO_LARGE","IMAGE_DIMENSIONS_TOO_LARGE").contains(code)?413:415,code,"图片格式、大小或分辨率不符合要求");
            }
            String mime=metadata.path("mimeType").asText();
            String suffix=switch(mime){case "image/png"->".png";case "image/jpeg"->".jpg";case "image/webp"->".webp";default->throw new ApiException(415,"UNSUPPORTED_IMAGE_TYPE","仅支持静态JPG、PNG或WebP");};
            String key=UUID.randomUUID()+suffix;
            saved=uploads.resolve(key);Files.move(temporary,saved);
            String name=upload.getOriginalFilename()==null?"image":upload.getOriginalFilename();
            if(name.length()>255)name=name.substring(0,255);
            long id=SqlSupport.insert(db,"INSERT INTO stored_file(uploaded_by,storage_key,original_name,sha256,mime_type,size_bytes,width,height,created_at) VALUES(?,?,?,?,?,?,?,?,UTC_TIMESTAMP(3))",user.userId(),key,name,HexFormat.of().formatHex(digest.digest()),mime,size,metadata.path("width").asInt(),metadata.path("height").asInt());
            saved=null;
            return new UploadedFile(Long.toString(id),mime,metadata.path("width").asInt(),metadata.path("height").asInt(),size);
        } finally {Files.deleteIfExists(temporary);if(saved!=null)Files.deleteIfExists(saved);}
    }
    private Map<String,Object> file(String id) {
        if(id==null || !id.matches("[1-9][0-9]{0,18}"))throw missing();
        var rows=db.queryForList("SELECT * FROM stored_file WHERE id=?",id);
        if(rows.isEmpty())throw missing();return rows.getFirst();
    }
    private ApiException missing(){return new ApiException(404,"RESOURCE_NOT_FOUND","未找到可访问的文件");}
    public void requireBindable(CurrentUser user,String fileId) {
        var row=file(fileId);
        int bindings=db.queryForObject("SELECT COUNT(*) FROM file_binding WHERE file_id=?",Integer.class,fileId);
        if(bindings==0 && row.get("uploaded_by").toString().equals(user.userId()))return;
        int ownedBody=db.queryForObject("SELECT COUNT(*) FROM file_binding b JOIN manuscript m ON m.id=b.draft_manuscript_id JOIN organization_member om ON om.organization_id=m.organization_id WHERE b.file_id=? AND b.purpose='BODY_IMAGE' AND om.user_id=? AND om.enabled=true AND m.deleted_at IS NULL",Integer.class,fileId,user.userId());
        if(ownedBody>0 && user.role()==CurrentUser.Role.MEMBER)return;
        if(user.role()==CurrentUser.Role.ADMIN && row.get("uploaded_by").toString().equals(user.userId()) && db.queryForObject("SELECT COUNT(*) FROM file_binding WHERE file_id=? AND purpose='BODY_IMAGE'",Integer.class,fileId)>0)return;
        throw missing();
    }
    public ReadableFile read(CurrentUser user,String id) {
        var row=file(id);
        var bindings=db.queryForList("SELECT * FROM file_binding WHERE file_id=?",id);
        boolean allowed=bindings.isEmpty() && row.get("uploaded_by").toString().equals(user.userId());
        for(var binding:bindings) {
            if("EVIDENCE_IMAGE".equals(binding.get("purpose"))) {if(user.role()==CurrentUser.Role.REVIEWER)allowed=true;continue;}
            if(!"BODY_IMAGE".equals(binding.get("purpose")))continue;
            if(binding.get("reference_revision_id")!=null) {if(user.role()==CurrentUser.Role.ADMIN || user.role()==CurrentUser.Role.REVIEWER)allowed=true;continue;}
            boolean submission=binding.get("submission_version_id")!=null;
            String query=submission ? "SELECT m.* FROM manuscript m JOIN submission_version v ON v.manuscript_id=m.id WHERE v.id=?" : "SELECT * FROM manuscript WHERE id=?";
            Object objectId=binding.get(submission?"submission_version_id":"draft_manuscript_id");
            var manuscripts=db.queryForList(query,objectId);
            for(var m:manuscripts) {
                if(submission && "PUBLISHED".equals(m.get("publication_state")) && Objects.equals(m.get("published_version_id"),binding.get("submission_version_id")))allowed=true;
                if(submission && user.role()==CurrentUser.Role.REVIEWER)allowed=true;
                if(user.role()==CurrentUser.Role.MEMBER && user.organizationIds().contains(m.get("organization_id").toString()) && m.get("deleted_at")==null)allowed=true;
            }
        }
        if(!allowed)throw missing();
        var folder=settings.runtime().resolve("uploads").normalize();
        var path=folder.resolve(row.get("storage_key").toString()).normalize();
        if(!path.startsWith(folder) || !Files.isRegularFile(path))throw missing();
        return new ReadableFile(path,row.get("mime_type").toString(),((Number)row.get("size_bytes")).longValue());
    }
}
