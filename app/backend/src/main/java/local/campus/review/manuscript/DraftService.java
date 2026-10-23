package local.campus.review.manuscript;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.content.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;
import static local.campus.review.content.DocumentModels.*;

@Service
public class DraftService {
    private final JdbcTemplate db;
    private final DocumentCodec codec;
    private final FileService files;
    private final ObjectMapper json;
    public DraftService(JdbcTemplate db,DocumentCodec codec,FileService files,ObjectMapper json){this.db=db;this.codec=codec;this.files=files;this.json=json;}
    private String encode(Object value){try{return json.writeValueAsString(value);}catch(Exception e){throw new IllegalArgumentException("Invalid document",e);}}
    public Map<String,Object> requireDraft(CurrentUser user,String id,boolean lock) {
        if(id==null || !id.matches("[1-9][0-9]{0,18}"))throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到稿件");
        var rows=db.queryForList("SELECT * FROM manuscript WHERE id=? AND deleted_at IS NULL"+(lock?" FOR UPDATE":""),id);
        if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到稿件");
        var manuscript=rows.getFirst();AccessPolicy.requireOrganization(user,manuscript.get("organization_id").toString());
        if(!Set.of("DRAFT","RETURNED").contains(manuscript.get("status").toString()))throw new ApiException(409,"INVALID_STATE","当前稿件状态不允许编辑");
        return manuscript;
    }
    @Transactional public Map<String,Object> create(CurrentUser user,String organizationId,String title) {
        AccessPolicy.requireOrganization(user,organizationId);
        var document=new DocumentInput(title==null?"":title,"1",json.createObjectNode().put("type","doc").set("content",json.createArrayNode()),List.of());
        var extracted=codec.validateAndExtract(document);
        long id=SqlSupport.insert(db,"INSERT INTO manuscript(organization_id,created_by,status,publication_state,next_version_no,reprint_allowed,created_at,updated_at) VALUES(?,?,'DRAFT','NOT_PUBLISHED',1,true,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",organizationId,user.userId());
        db.update("INSERT INTO manuscript_draft(manuscript_id,title,schema_version,content_json,sources_json,content_sha256,revision,updated_by,updated_at) VALUES(?,?,'1',?,?,?,0,?,UTC_TIMESTAMP(3))",id,document.title(),encode(extracted.document().content()),"[]",extracted.contentHash(),user.userId());
        event(user,Long.toString(id),organizationId,"MANUSCRIPT_CREATED",Map.of());
        return Map.of("manuscriptId",Long.toString(id),"draftRevision","0");
    }
    public Map<String,Object> get(CurrentUser user,String id) {
        var manuscript=requireDraft(user,id,false);
        var row=db.queryForMap("SELECT * FROM manuscript_draft WHERE manuscript_id=?",id);
        return response(id,manuscript,row);
    }
    private Map<String,Object> response(String id,Map<String,Object> manuscript,Map<String,Object> row) {
        try {
            var result=new LinkedHashMap<String,Object>();result.put("manuscriptId",id);result.put("organizationId",manuscript.get("organization_id").toString());result.put("status",manuscript.get("status"));
            result.put("title",row.get("title"));result.put("schemaVersion",row.get("schema_version"));result.put("revision",row.get("revision").toString());
            result.put("content",json.readTree(row.get("content_json").toString()));result.put("sources",json.readTree(row.get("sources_json").toString()));
            result.put("savedAt",((LocalDateTime)row.get("updated_at")).atOffset(ZoneOffset.UTC).toString());return result;
        }catch(Exception e){throw new IllegalStateException("Saved draft could not be read",e);}
    }
    @Transactional public Map<String,Object> save(CurrentUser user,String id,long expectedRevision,DocumentInput input) {
        var manuscript=requireDraft(user,id,true);
        var result=codec.validateAndExtract(input);
        for(var image:result.images())files.requireBindable(user,image.fileId());
        int changed=db.update("UPDATE manuscript_draft SET title=?,schema_version=?,content_json=?,sources_json=?,content_sha256=?,revision=revision+1,updated_by=?,updated_at=UTC_TIMESTAMP(3) WHERE manuscript_id=? AND revision=?",input.title(),result.schemaVersion(),encode(result.document().content()),encode(result.document().sources()),result.contentHash(),user.userId(),id,expectedRevision);
        if(changed!=1)throw new ApiException(409,"DRAFT_REVISION_CONFLICT","另一窗口已更新稿件，当前内容仍保留，请核对后重试");
        db.update("DELETE FROM file_binding WHERE draft_manuscript_id=?",id);
        for(var image:result.images())db.update("INSERT INTO file_binding(file_id,draft_manuscript_id,node_id,purpose) VALUES(?,?,?,'BODY_IMAGE')",image.fileId(),id,image.nodeId());
        db.update("UPDATE manuscript SET updated_at=UTC_TIMESTAMP(3) WHERE id=?",id);
        event(user,id,manuscript.get("organization_id").toString(),"DRAFT_SAVED",Map.of("saveKind","MANUAL","revision",Long.toString(expectedRevision+1)));
        return get(user,id);
    }
    @Transactional public Map<String,Object> delete(CurrentUser user,String id){
        var manuscript=requireDraft(user,id,true);
        if(!"DRAFT".equals(manuscript.get("status")))throw new ApiException(409,"INVALID_STATE","只有草稿允许删除");
        db.update("UPDATE manuscript SET deleted_at=UTC_TIMESTAMP(3),updated_at=UTC_TIMESTAMP(3) WHERE id=?",id);
        event(user,id,manuscript.get("organization_id").toString(),"DRAFT_DELETED",Map.of());return Map.of("deleted",true);
    }
    private void event(CurrentUser user,String manuscriptId,String organizationId,String operation,Map<String,Object> fields) {
        var details=new LinkedHashMap<String,Object>(fields);details.put("schemaVersion","1");details.put("actorName",user.displayName());
        details.put("organizationName",db.queryForObject("SELECT name FROM organization WHERE id=?",String.class,organizationId));
        db.update("INSERT INTO operation_log(actor_id,organization_id,object_type,object_id,operation,details_json,created_at) VALUES(?,?,'MANUSCRIPT',?,?,?,UTC_TIMESTAMP(3))",user.userId(),organizationId,manuscriptId,operation,encode(details));
    }
}
