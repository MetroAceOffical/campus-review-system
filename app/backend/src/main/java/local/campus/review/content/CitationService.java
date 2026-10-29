package local.campus.review.content;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import java.util.*;
import static local.campus.review.content.DocumentModels.*;

@Service
public class CitationService {
    private final JdbcTemplate db;private final ObjectMapper json;private final DocumentCodec codec;
    public CitationService(JdbcTemplate db,ObjectMapper json,DocumentCodec codec){this.db=db;this.json=json;this.codec=codec;}
    private String visible(CurrentUser user){return user.role()==CurrentUser.Role.ADMIN || user.role()==CurrentUser.Role.REVIEWER?"1=1":"(w.origin_type='PUBLISHED' AND m.publication_state='PUBLISHED')";}
    private final String from=" FROM reference_revision r JOIN reference_work w ON w.id=r.reference_work_id LEFT JOIN manuscript m ON m.id=w.manuscript_id LEFT JOIN organization o ON o.id=m.organization_id WHERE w.enabled=true AND ";
    public JsonNode departments(){return json.valueToTree(db.queryForList("SELECT CAST(id AS CHAR) AS id,name FROM organization WHERE enabled=true ORDER BY id"));}
    public JsonNode search(CurrentUser user,String q,String department,int page){
        if(q.length()>200 || page<1 || department.length()>20 || (!department.isEmpty() && !department.matches("[1-9][0-9]{0,18}")))throw new ApiException(400,"VALIDATION_ERROR","来源搜索参数无效");
        String sql=from+visible(user)+" AND r.revision_no=(SELECT MAX(x.revision_no) FROM reference_revision x WHERE x.reference_work_id=w.id) AND r.title LIKE ?";
        var args=new ArrayList<Object>(List.of("%"+q+"%"));if(!department.isEmpty()){sql+=" AND m.organization_id=?";args.add(department);}
        var result=json.createObjectNode().put("total",db.queryForObject("SELECT COUNT(*)"+sql,Long.class,args.toArray()));var items=result.putArray("items");args.add((page-1L)*10);
        for(var row:db.queryForList("SELECT r.id,r.reference_work_id,r.title,r.artifacts_json,r.content_json,o.name AS department"+sql+" ORDER BY r.created_at DESC,r.id DESC LIMIT 10 OFFSET ?",args.toArray())){
            var item=items.addObject().put("workId",row.get("reference_work_id").toString()).put("revisionId",row.get("id").toString()).put("title",row.get("title").toString()).put("department",Objects.toString(row.get("department"),"参考材料"));
            String text=JsonSupport.parse(json,row.get("artifacts_json").toString()).path("plainText").asText();item.put("preview",text.substring(0,Math.min(300,text.length())));
        }return result;
    }
    Map<String,Object> target(CurrentUser user,String revision,String work){
        if(revision==null || !revision.matches("[1-9][0-9]{0,18}"))throw new ApiException(404,"RESOURCE_NOT_FOUND","来源不可访问");
        var rows=db.queryForList("SELECT r.*,w.manuscript_id"+from+visible(user)+" AND r.id=?",revision);
        if(rows.isEmpty() || (work!=null && !work.equals(rows.getFirst().get("reference_work_id").toString())))throw new ApiException(404,"RESOURCE_NOT_FOUND","来源不可访问");return rows.getFirst();
    }
    public JsonNode get(CurrentUser user,String revision){
        var row=target(user,revision,null);var metadata=JsonSupport.parse(json,row.get("source_metadata_json").toString());
        var result=json.createObjectNode().put("title",row.get("title").toString()).put("schemaVersion","2").put("workId",row.get("reference_work_id").toString()).put("revisionId",revision);
        result.set("content",JsonSupport.parse(json,row.get("content_json").toString()));result.set("sources",metadata.path("bodySources").isArray()?metadata.get("bodySources"):json.createArrayNode());return result;
    }
    public DocumentInput normalize(CurrentUser user,DocumentInput input){
        if(input==null || input.sources()==null)return input;
        var sources=new ArrayList<Source>();
        for(var source:input.sources()){
            if(source!=null && "INTERNAL".equals(source.kind())){var row=target(user,source.revisionId(),source.workId());sources.add(new Source(source.sourceId(),"","INTERNAL",source.workId(),source.revisionId(),row.get("title").toString()));}
            else sources.add(source);
        }return new DocumentInput(input.title(),input.schemaVersion(),input.content(),sources);
    }
    public void annotate(JsonNode evidence,ExtractedDocument document){
        var sources=new HashMap<String,Source>();for(var source:document.document().sources())sources.put(source.sourceId(),source);
        for(var item:evidence){
            if(!item.isObject() || !"TEXT_SIMILARITY".equals(item.path("evidenceType").asText()))continue;
            var supporting=semanticSupport(item);int relevant=0,uncovered=0;var states=((ObjectNode)item).putArray("citationChecks");
            for(String field:List.of("matches","semanticWindows"))for(var match:item.path(field)){
                boolean warning=field.equals("matches")?item.path("acceptedCandidate").asBoolean():item.path("semanticSummary").path("suspectedReuse").asBoolean() && supporting.contains(match);
                int start=match.path("queryStart").asInt(-1),end=match.path("queryEnd").asInt(-1);if(start<0 || end<=start)continue;
                var cuts=new TreeSet<Integer>(List.of(start,end));
                for(var span:document.citations())if(span.plainStart()<end && span.plainEnd()>start){cuts.add(Math.max(start,span.plainStart()));cuts.add(Math.min(end,span.plainEnd()));}
                var points=new ArrayList<>(cuts);for(int i=0;i+1<points.size();i++){
                    int left=points.get(i),right=points.get(i+1);
                    if(InspectionService.slice(document.plainText(),left,right).codePoints().allMatch(c->Character.isWhitespace(c)||Character.isSpaceChar(c)))continue;
                    var covers=document.citations().stream().filter(c->c.plainStart()<=left && c.plainEnd()>=right).map(c->sources.get(c.sourceId())).filter(Objects::nonNull).toList();
                    boolean same=covers.stream().anyMatch(s->"INTERNAL".equals(s.kind()) && item.path("sourceWorkId").asText().equals(s.workId()));
                    String status=same?"CITED":covers.stream().anyMatch(s->"INTERNAL".equals(s.kind()))?"SOURCE_MISMATCH":covers.isEmpty()?"UNCITED":"EXTERNAL_REVIEW";
                    states.addObject().put("queryStart",left).put("queryEnd",right).put("status",status).put("evidenceField",field);
                    if(warning){relevant++;if(!same)uncovered++;}
                }
            }
            ((ObjectNode)item).put("fullyCited",relevant>0 && uncovered==0);((ObjectNode)item).put("citationVerifiedSegments",relevant-uncovered);((ObjectNode)item).put("citationPolicyVersion","occurrence-aware-v2");
        }
    }
    private List<JsonNode> semanticSupport(JsonNode item){
        var summary=item.path("semanticSummary");var windows=new ArrayList<JsonNode>();item.path("semanticWindows").forEach(windows::add);
        windows.sort(Comparator.<JsonNode>comparingDouble(w->-w.path("score").asDouble()).thenComparingDouble(w->-w.path("tfidfScore").asDouble()).thenComparingInt(w->w.path("queryStart").asInt()));
        var selected=new ArrayList<JsonNode>();for(var window:windows){
            if(!qualifies(window,summary))continue;
            if(selected.stream().anyMatch(old->overlap(window,old,"query") || overlap(window,old,"source")))continue;selected.add(window);
        }
        // Source overlap limits independent support for the reuse decision. It
        // must not hide another occurrence from per-position citation checking.
        var occurrences=new ArrayList<JsonNode>(selected);
        for(var window:windows)if(qualifies(window,summary) && !occurrences.contains(window) && selected.stream().anyMatch(old->sameTextPair(window,old)))occurrences.add(window);
        return occurrences;
    }
    private boolean qualifies(JsonNode window,JsonNode summary){return window.path("score").asDouble()>=summary.path("scoreThreshold").asDouble(.5) && window.path("tfidfScore").asDouble()>=summary.path("lexicalFloor").asDouble(.25) && window.path("queryEnd").asInt()-window.path("queryStart").asInt()>=12;}
    private boolean sameTextPair(JsonNode a,JsonNode b){return a.path("queryText").isTextual() && a.path("sourceText").isTextual() && !a.path("queryText").asText().isBlank() && !a.path("sourceText").asText().isBlank() && a.get("queryText").equals(b.path("queryText")) && a.get("sourceText").equals(b.path("sourceText"));}
    private boolean overlap(JsonNode a,JsonNode b,String prefix){return a.path(prefix+"Start").asInt()<b.path(prefix+"End").asInt() && b.path(prefix+"Start").asInt()<a.path(prefix+"End").asInt();}
}
