package local.campus.review.content;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.manuscript.DraftService;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import static local.campus.review.content.DocumentModels.*;

@Service
public class InspectionService {
    final JdbcTemplate db;final ObjectMapper json;final RuntimeSettings settings;final DocumentCodec codec;final CitationService citations;
    private final DraftService drafts;private final FileService files;
    final Map<String,Process> processes=new ConcurrentHashMap<>();
    public InspectionService(JdbcTemplate db,ObjectMapper json,RuntimeSettings settings,DocumentCodec codec,CitationService citations,DraftService drafts,FileService files){this.db=db;this.json=json;this.settings=settings;this.codec=codec;this.citations=citations;this.drafts=drafts;this.files=files;}
    static final Set<String> KINDS=Set.of("CONTENT","GRAMMAR_RULES","GRAMMAR_MODEL","IMAGE_TEXT");
    static final Set<String> DONE=Set.of("COMPLETED","FAILED","CANCELLED","INTERRUPTED");
    private ApiException missing(){return new ApiException(404,"RESOURCE_NOT_FOUND","未找到可访问的稿件检查");}
    private void access(CurrentUser user,String manuscript,boolean submitted){
        if(manuscript==null || !manuscript.matches("[1-9][0-9]{0,18}"))throw missing();
        var rows=db.queryForList("SELECT organization_id FROM manuscript WHERE id=? AND deleted_at IS NULL",manuscript);if(rows.isEmpty())throw missing();
        if(user.role()==CurrentUser.Role.REVIEWER){if(!submitted)throw missing();}else AccessPolicy.requireOrganization(user,rows.getFirst().get("organization_id").toString());
    }
    public JsonNode draft(CurrentUser user,String id,String kind,DocumentInput input)throws Exception{drafts.requireDraft(user,id,false);return create(user,id,null,kind,citations.normalize(user,input));}
    public JsonNode submission(CurrentUser user,String version,String kind)throws Exception{
        var rows=db.queryForList("SELECT * FROM submission_version WHERE id=?",version);if(rows.isEmpty())throw missing();var row=rows.getFirst();access(user,row.get("manuscript_id").toString(),true);
        var input=new DocumentInput(row.get("title").toString(),row.get("schema_version").toString(),JsonSupport.parse(json,row.get("content_json").toString()),json.convertValue(JsonSupport.parse(json,row.get("sources_json").toString()),new com.fasterxml.jackson.core.type.TypeReference<List<Source>>(){}));
        return create(user,row.get("manuscript_id").toString(),version,kind,input);
    }
    private JsonNode create(CurrentUser user,String manuscript,String version,String kind,DocumentInput input)throws Exception{
        if(kind==null || !KINDS.contains(kind))throw new ApiException(400,"VALIDATION_ERROR","请选择检查类型");
        var document=codec.validateAndExtract(input);
        if(document.plainText().isBlank() && document.images().isEmpty())throw new ApiException(400,"VALIDATION_ERROR","请先填写正文或添加配图");
        var active=db.queryForList("SELECT id FROM document_check WHERE manuscript_id=? AND kind=? AND input_sha256=? AND status IN ('QUEUED','RUNNING','WAITING_SERVICE','WAITING_RESOURCE') ORDER BY created_at DESC LIMIT 1",manuscript,kind,document.contentHash());if(!active.isEmpty())return get(user,active.getFirst().get("id").toString());
        String id=UUID.randomUUID().toString();
        var payload=json.createObjectNode().put("checkId",id).put("kind",kind).put("inputHash",document.contentHash()).put("title",input.title()).put("plainText",document.plainText()).put("manuscriptId",manuscript).put("runtime",settings.runtime().toString());
        payload.set("document",json.valueToTree(document.document()));payload.set("positionMap",json.valueToTree(document.positionMap()));payload.set("citations",json.valueToTree(document.citations()));
        var blocks=new ArrayList<JsonNode>();collect(document.document().content(),blocks);var images=payload.putArray("images");
        for(var picture:document.images()){
            var file=files.read(user,picture.fileId());String digest;try(var stream=Files.newInputStream(file.path())){var hash=java.security.MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[65536];int n;while((n=stream.read(buffer))!=-1)hash.update(buffer,0,n);digest=HexFormat.of().formatHex(hash.digest());}
            var output=images.addObject().put("nodeId",picture.nodeId()).put("fileId",picture.fileId()).put("caption",picture.caption()).put("path",file.path().toString()).put("sha256",digest);
            var contexts=output.putArray("contexts");if(!input.title().isBlank())contexts.addObject().put("field","TITLE").put("text",input.title()).put("label","稿件标题");if(!picture.caption().isBlank())contexts.addObject().put("field","CAPTION").put("text",picture.caption()).put("label","图片图注");
            for(var block:blocks)if(!"campusImage".equals(block.path("type").asText())){
                String node=block.path("attrs").path("nodeId").asText();var positions=document.positionMap().stream().filter(p->p.nodeId().equals(node)).toList();if(positions.isEmpty())continue;
                int start=positions.getFirst().plainStart(),end=positions.getLast().plainEnd();String text=slice(document.plainText(),start,end);
                for(int offset=0;offset<DocumentCodec.points(text);offset+=180){int right=Math.min(DocumentCodec.points(text),offset+180);contexts.addObject().put("field","BODY").put("nodeId",node).put("start",start+offset).put("end",start+right).put("label","正文段落").put("text",slice(text,offset,right));}
            }
            int index=-1;for(int i=0;i<blocks.size();i++)if(picture.nodeId().equals(blocks.get(i).path("attrs").path("nodeId").asText()))index=i;
            var adjacent=new StringBuilder(picture.caption());for(int direction:new int[]{-1,1})for(int i=index+direction;i>=0 && i<blocks.size();i+=direction){var block=blocks.get(i);if("campusImage".equals(block.path("type").asText()))break;String node=block.path("attrs").path("nodeId").asText();var positions=document.positionMap().stream().filter(p->p.nodeId().equals(node)).toList();if(!positions.isEmpty()){adjacent.append('\n').append(slice(document.plainText(),positions.getFirst().plainStart(),positions.getLast().plainEnd()));break;}}
            output.put("factContext",adjacent.toString());
        }
        db.update("INSERT INTO document_check(id,manuscript_id,submission_version_id,kind,status,input_sha256,payload_json,created_by,created_at) VALUES(?,?,?,?,'QUEUED',?,?,?,UTC_TIMESTAMP(3))",id,manuscript,version,kind,document.contentHash(),payload.toString(),user.userId());event(id,Map.of("stage","QUEUED"));return get(user,id);
    }
    static String slice(String value,int from,int to){return value.substring(value.offsetByCodePoints(0,from),value.offsetByCodePoints(0,to));}
    private void collect(JsonNode node,List<JsonNode> blocks){if(Set.of("paragraph","heading","campusImage").contains(node.path("type").asText()))blocks.add(node);else for(var child:node.path("content"))collect(child,blocks);}
    Map<String,Object> require(CurrentUser user,String id){if(id==null || !id.matches("[a-f0-9-]{36}"))throw missing();var rows=db.queryForList("SELECT * FROM document_check WHERE id=?",id);if(rows.isEmpty())throw missing();var row=rows.getFirst();access(user,row.get("manuscript_id").toString(),row.get("submission_version_id")!=null);return row;}
    public JsonNode get(CurrentUser user,String id){var row=require(user,id);var result=(ObjectNode)response(row);var feedback=result.putObject("feedback");for(var event:db.queryForList("SELECT payload_json FROM document_check_event WHERE check_id=? AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.stage'))='FEEDBACK' AND JSON_UNQUOTE(JSON_EXTRACT(payload_json,'$.actorId'))=? ORDER BY id",id,user.userId())){var value=JsonSupport.parse(json,event.get("payload_json").toString());feedback.put(value.path("issueId").asText(),value.path("action").asText());}return result;}
    public JsonNode feedback(CurrentUser user,String id,String issueId,String action){
        var row=require(user,id);if(user.role()!=CurrentUser.Role.MEMBER || row.get("submission_version_id")!=null)throw new ApiException(403,"ACCESS_DENIED","只能对可编辑草稿采用建议");
        drafts.requireDraft(user,row.get("manuscript_id").toString(),false);if(action==null || !Set.of("ACCEPT","IGNORE").contains(action) || issueId==null || row.get("result_json")==null)throw new ApiException(400,"VALIDATION_ERROR","建议记录无效");
        boolean found=false;for(var issue:JsonSupport.parse(json,row.get("result_json").toString()).path("issues"))if(issueId.equals(issue.path("id").asText()))found=true;if(!found)throw new ApiException(400,"VALIDATION_ERROR","未找到该检查建议");
        event(id,Map.of("stage","FEEDBACK","actorId",user.userId(),"issueId",issueId,"action",action));return json.createObjectNode().put("saved",true);
    }
    JsonNode response(Map<String,Object> row){var payload=JsonSupport.parse(json,row.get("payload_json").toString());var result=json.createObjectNode().put("checkId",row.get("id").toString()).put("kind",row.get("kind").toString()).put("status",row.get("status").toString()).put("inputHash",row.get("input_sha256").toString()).put("error",Objects.toString(row.get("error_message"),""));result.set("positionMap",payload.path("positionMap"));result.set("document",payload.path("document"));if(row.get("result_json")!=null)result.set("result",JsonSupport.parse(json,row.get("result_json").toString()));return result;}
    public JsonNode list(CurrentUser user,String manuscript,String version){access(user,manuscript,version!=null);String sql="SELECT * FROM document_check WHERE manuscript_id=?";var args=new ArrayList<Object>(List.of(manuscript));if(version!=null){sql+=" AND submission_version_id=?";args.add(version);}sql+=" ORDER BY created_at DESC LIMIT 30";var result=json.createArrayNode();for(var row:db.queryForList(sql,args.toArray()))result.add(response(row));return result;}
    void event(String id,Object value){db.update("INSERT INTO document_check_event(check_id,payload_json,created_at) VALUES(?,?,UTC_TIMESTAMP(3))",id,JsonSupport.encode(json,value));}
    public JsonNode events(CurrentUser user,String id,long after){require(user,id);var result=json.createArrayNode();for(var row:db.queryForList("SELECT id,payload_json FROM document_check_event WHERE check_id=? AND id>? ORDER BY id LIMIT 500",id,Math.max(0,after)))result.addObject().put("sequence",((Number)row.get("id")).longValue()).set("data",JsonSupport.parse(json,row.get("payload_json").toString()));return result;}
    public JsonNode cancel(CurrentUser user,String id){require(user,id);db.update("UPDATE document_check SET status='CANCELLED',finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status IN ('QUEUED','WAITING_SERVICE','WAITING_RESOURCE','RUNNING')",id);var process=processes.get(id);if(process!=null)stop(process);return get(user,id);}
    static void stop(Process process){process.descendants().forEach(ProcessHandle::destroyForcibly);process.destroyForcibly();}
}
