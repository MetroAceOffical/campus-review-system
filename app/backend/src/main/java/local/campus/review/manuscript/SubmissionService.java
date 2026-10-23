package local.campus.review.manuscript;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.content.*;
import local.campus.review.content.DocumentModels.*;
import local.campus.review.detection.DetectionService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.*;
import java.util.*;

@Service
public class SubmissionService {
    private final JdbcTemplate db;private final ObjectMapper json;private final IdempotencyStore keys;
    private final DocumentCodec codec;private final FileService files;private final DetectionService detection;
    public SubmissionService(JdbcTemplate db,ObjectMapper json,IdempotencyStore keys,DocumentCodec codec,FileService files,DetectionService detection){this.db=db;this.json=json;this.keys=keys;this.codec=codec;this.files=files;this.detection=detection;}
    @Transactional public JsonNode submit(CurrentUser user,String id,String key,long expectedRevision,DocumentInput input){
        var rows=db.queryForList("SELECT * FROM manuscript WHERE id=? AND deleted_at IS NULL FOR UPDATE",id);
        if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到稿件");var manuscript=rows.getFirst();String organization=manuscript.get("organization_id").toString();AccessPolicy.requireOrganization(user,organization);
        var cached=keys.begin(user.userId(),"SUBMIT",key,JsonSupport.hash(json,Map.of("manuscriptId",id,"expectedRevision",expectedRevision,"input",input)));if(cached!=null)return cached;
        if(!Set.of("DRAFT","RETURNED").contains(manuscript.get("status")))throw new ApiException(409,"INVALID_STATE","当前稿件不允许送审");
        var draft=db.queryForMap("SELECT * FROM manuscript_draft WHERE manuscript_id=? FOR UPDATE",id);
        if(((Number)draft.get("revision")).longValue()!=expectedRevision)throw new ApiException(409,"DRAFT_REVISION_CONFLICT","其他窗口已修改稿件，请核对内容");
        var extracted=codec.validateForSubmission(input);for(var image:extracted.images())files.requireBindable(user,image.fileId());
        String content=JsonSupport.encode(json,extracted.document().content()),sources=JsonSupport.encode(json,extracted.document().sources());
        db.update("UPDATE manuscript_draft SET title=?,schema_version=?,content_json=?,sources_json=?,content_sha256=?,revision=revision+1,updated_by=?,updated_at=UTC_TIMESTAMP(3) WHERE manuscript_id=?",input.title(),extracted.schemaVersion(),content,sources,extracted.contentHash(),user.userId(),id);
        db.update("DELETE FROM file_binding WHERE draft_manuscript_id=?",id);
        for(var image:extracted.images())db.update("INSERT INTO file_binding(file_id,draft_manuscript_id,node_id,purpose) VALUES(?,?,?,'BODY_IMAGE')",image.fileId(),id,image.nodeId());
        int number=((Number)manuscript.get("next_version_no")).intValue();
        long version=SqlSupport.insert(db,"INSERT INTO submission_version(manuscript_id,version_no,schema_version,extractor_version,title,content_json,sources_json,plain_text,position_map_json,content_sha256,lifecycle_status,submitted_by,submitted_at) VALUES(?,?,?,?,?,?,?,?,?,?,'PENDING',?,UTC_TIMESTAMP(3))",id,number,extracted.schemaVersion(),extracted.extractorVersion(),input.title(),content,sources,extracted.plainText(),JsonSupport.encode(json,extracted.positionMap()),extracted.contentHash(),user.userId());
        for(var image:extracted.images())db.update("INSERT INTO file_binding(file_id,submission_version_id,node_id,purpose) VALUES(?,?,?,'BODY_IMAGE')",image.fileId(),version,image.nodeId());
        String batch=detection.createFormalBatch(Long.toString(version),extracted.contentHash());
        db.update("UPDATE manuscript SET status='PENDING',current_submission_id=?,next_version_no=next_version_no+1,updated_at=UTC_TIMESTAMP(3) WHERE id=?",version,id);
        var details=Map.of("schemaVersion","1","actorName",user.displayName(),"organizationName",db.queryForObject("SELECT name FROM organization WHERE id=?",String.class,organization),"versionNo",number,"saveKind","SUBMIT");
        db.update("INSERT INTO operation_log(actor_id,organization_id,object_type,object_id,version_id,operation,details_json,created_at) VALUES(?,?,'MANUSCRIPT',?,?,'SUBMITTED',?,UTC_TIMESTAMP(3))",user.userId(),organization,id,version,JsonSupport.encode(json,details));
        var receipt=json.valueToTree(Map.of("submissionId",Long.toString(version),"versionNo",number,"batchId",batch,"status","PENDING","draftRevision",Long.toString(expectedRevision+1)));
        keys.complete(user.userId(),"SUBMIT",key,receipt);return receipt;
    }
    public JsonNode get(CurrentUser user,String id){
        var rows=db.queryForList("SELECT v.*,m.organization_id FROM submission_version v JOIN manuscript m ON m.id=v.manuscript_id WHERE v.id=?",id);if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到送审版本");var row=rows.getFirst();
        if(user.role()!=CurrentUser.Role.REVIEWER)AccessPolicy.requireOrganization(user,row.get("organization_id").toString());
        var result=json.createObjectNode().put("submissionId",id).put("manuscriptId",row.get("manuscript_id").toString()).put("versionNo",((Number)row.get("version_no")).intValue()).put("title",row.get("title").toString()).put("schemaVersion",row.get("schema_version").toString()).put("lifecycleStatus",row.get("lifecycle_status").toString()).put("submittedAt",((LocalDateTime)row.get("submitted_at")).atOffset(ZoneOffset.UTC).toString());
        result.set("content",JsonSupport.parse(json,row.get("content_json").toString()));result.set("sources",JsonSupport.parse(json,row.get("sources_json").toString()));
        if(user.role()==CurrentUser.Role.REVIEWER){result.put("plainText",row.get("plain_text").toString());result.set("positionMap",JsonSupport.parse(json,row.get("position_map_json").toString()));}
        var decisions=db.queryForList("SELECT id,decision,reason,decided_at FROM review_decision WHERE submission_version_id=?",id);
        if(!decisions.isEmpty()){var decision=decisions.getFirst();var value=json.createObjectNode().put("decisionId",decision.get("id").toString()).put("decision",decision.get("decision").toString()).put("reason",Objects.toString(decision.get("reason"),"")).put("decidedAt",((LocalDateTime)decision.get("decided_at")).atOffset(ZoneOffset.UTC).toString());result.set("decision",value);}else result.putNull("decision");
        return result;
    }
}
