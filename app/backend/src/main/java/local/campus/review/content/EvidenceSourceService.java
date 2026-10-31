package local.campus.review.content;
import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import local.campus.review.detection.DetectionQueryService;
import local.campus.review.reference.LibraryGenerationService;
import org.springframework.stereotype.Service;

/** Reads only an exact historical source already present in an authorized report. */
@Service
public class EvidenceSourceService {
    private final DetectionQueryService reports;private final InspectionService checks;private final LibraryGenerationService libraries;private final ObjectMapper json;
    public EvidenceSourceService(DetectionQueryService reports,InspectionService checks,LibraryGenerationService libraries,ObjectMapper json){this.reports=reports;this.checks=checks;this.libraries=libraries;this.json=json;}
    static ApiException missing(){return new ApiException(404,"RESOURCE_NOT_FOUND","该报告中未找到对应来源全文");}
    static JsonNode findSource(JsonNode evidence,JsonNode library){
        for(var source:library.path("documents")){
            if(!evidence.path("sourceWorkId").asText().isBlank()&&evidence.path("sourceWorkId").asText().equals(source.path("sourceWorkId").asText())&&evidence.path("sourceRevisionId").asText().equals(source.path("sourceRevisionId").asText())&&evidence.path("sourceKind").asText("BODY").equals(source.path("sourceKind").asText("BODY"))&&(!evidence.hasNonNull("sourceKey")||evidence.path("sourceKey").asText().equals(source.path("sourceKey").asText())))return source;
        }
        throw missing();
    }
    public JsonNode get(CurrentUser user,String batch,String check,String evidenceId){
        if((batch==null)==(check==null)||evidenceId==null||evidenceId.length()>200)throw missing();
        JsonNode evidence=null;String generation;
        if(batch!=null){
            var report=reports.report(user,batch);generation=report.path("libraryGenerationId").asText();
            for(var item:report.path("items"))for(var row:item.path("evidence"))if(evidenceId.equals(row.path("evidenceId").asText()))evidence=row;
        }else{
            var report=checks.get(user,check);generation=report.path("result").path("libraryGenerationId").asText();
            for(var row:report.path("result").path("evidence"))if(evidenceId.equals(row.path("evidenceId").asText()))evidence=row;
        }
        if(evidence==null||!"TEXT_SIMILARITY".equals(evidence.path("evidenceType").asText())||!generation.matches("[1-9][0-9]*"))throw missing();
        var source=findSource(evidence,libraries.lockedManifest(generation));
        var result=json.createObjectNode().put("evidenceId",evidenceId).put("sourceWorkId",source.path("sourceWorkId").asText()).put("sourceRevisionId",source.path("sourceRevisionId").asText()).put("sourceKind",source.path("sourceKind").asText("BODY")).put("title",source.path("title").asText(evidence.path("sourceTitle").asText())).put("plainText",source.path("text").asText()).put("url",evidence.path("sourceUrl").asText()).put("libraryGenerationId",generation);
        return result;
    }
}
