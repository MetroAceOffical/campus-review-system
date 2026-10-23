package local.campus.review.reference;

import com.fasterxml.jackson.databind.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

@Service
public class LibraryGenerationService {
    private final JdbcTemplate db;private final RuntimeSettings settings;private final ObjectMapper json;
    public LibraryGenerationService(JdbcTemplate db,RuntimeSettings settings,ObjectMapper json){this.db=db;this.settings=settings;this.json=json;}
    @Transactional public String reserve(){
        long id=SqlSupport.insert(db,"INSERT INTO library_generation(status,index_location,manifest_location,manifest_sha256,created_at) VALUES('BUILDING','','',?,UTC_TIMESTAMP(3))","0".repeat(64));
        Path directory=settings.runtime().resolve("indexes").resolve(Long.toString(id));
        db.update("UPDATE library_generation SET index_location=?,manifest_location=? WHERE id=?",directory.toString(),directory.resolve("manifest.json").toString(),id);
        return Long.toString(id);
    }
    public String currentId(){
        var rows=db.queryForList("SELECT library_generation_id FROM runtime_state WHERE name='CURRENT_LIBRARY'");
        return rows.isEmpty() || rows.getFirst().get("library_generation_id")==null ? null : rows.getFirst().get("library_generation_id").toString();
    }
    private Map<String,Object> generation(String id,boolean lock){
        var rows=db.queryForList("SELECT * FROM library_generation WHERE id=?"+(lock?" FOR UPDATE":""),id);
        if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到索引版本");return rows.getFirst();
    }
    private JsonNode verify(Map<String,Object> row,String hash){
        try{
            var root=settings.runtime().resolve("indexes").toAbsolutePath().normalize();
            var file=Path.of(row.get("manifest_location").toString()).toAbsolutePath().normalize();
            if(!file.startsWith(root) || !Files.isRegularFile(file))throw new IllegalStateException();
            String actual=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));
            if(!actual.equals(hash) || !actual.equals(Files.readString(file.getParent().resolve("READY")).trim()))throw new IllegalStateException();
            var manifest=json.readTree(Files.readString(file));
            if(!row.get("id").toString().equals(manifest.path("generationId").asText()))throw new IllegalStateException();
            return manifest;
        }catch(Exception e){throw new ApiException(409,"INDEX_NOT_READY","索引未完整准备或校验失败，继续保留原版本");}
    }
    @Transactional public void markReady(String id,String hash){
        var row=generation(id,true);if(!"BUILDING".equals(row.get("status")))throw new ApiException(409,"INVALID_STATE","索引不处于构建状态");
        verify(row,hash);db.update("UPDATE library_generation SET status='READY',manifest_sha256=? WHERE id=? AND status='BUILDING'",hash,id);
    }
    @Transactional public void activate(String id,String expectedCurrentId){
        db.update("INSERT IGNORE INTO runtime_state(name,library_generation_id,updated_at) VALUES('CURRENT_LIBRARY',NULL,UTC_TIMESTAMP(3))");
        var pointer=db.queryForMap("SELECT library_generation_id FROM runtime_state WHERE name='CURRENT_LIBRARY' FOR UPDATE");
        String current=pointer.get("library_generation_id")==null?null:pointer.get("library_generation_id").toString();
        if(!Objects.equals(current,expectedCurrentId))throw new ApiException(409,"LIBRARY_VERSION_CONFLICT","当前参考库已切换，请重新读取后重试");
        var row=generation(id,true);if(!"READY".equals(row.get("status")))throw new ApiException(409,"INDEX_NOT_READY","索引尚未准备完成");
        verify(row,row.get("manifest_sha256").toString());
        if(current!=null)db.update("UPDATE library_generation SET status='ARCHIVED' WHERE id=? AND status='ACTIVE'",current);
        db.update("UPDATE library_generation SET status='ACTIVE',activated_at=UTC_TIMESTAMP(3) WHERE id=? AND status='READY'",id);
        db.update("UPDATE runtime_state SET library_generation_id=?,updated_at=UTC_TIMESTAMP(3) WHERE name='CURRENT_LIBRARY'",id);
    }
    public JsonNode currentManifest(){String id=currentId();return id==null?json.createObjectNode():verify(generation(id,false),generation(id,false).get("manifest_sha256").toString());}
    public void fail(String id,String errorCode){
        db.update("UPDATE library_generation SET status='FAILED' WHERE id=? AND status='BUILDING'",id);
        try{var folder=settings.runtime().resolve("indexes").resolve(id);Files.createDirectories(folder);Files.writeString(folder.resolve("FAILED"),errorCode);}catch(Exception e){throw new IllegalStateException("Failed index marker could not be recorded",e);}
    }
}
