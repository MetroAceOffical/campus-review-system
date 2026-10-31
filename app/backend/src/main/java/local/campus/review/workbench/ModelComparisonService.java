package local.campus.review.workbench;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

/** Two ordinary evaluation runs over one immutable test partition. */
@Service
public class ModelComparisonService {
    final DatasetService data;final TrainingService training;
    public ModelComparisonService(DatasetService data,TrainingService training){this.data=data;this.training=training;}
    public record Start(String datasetId,String versionId,String preparationId){}
    @Transactional public JsonNode create(CurrentUser actor,String modelId,Start input){
        var model=training.model(actor,modelId);String parent=Objects.toString(model.get("parent_model_id"),"");
        if(parent.isEmpty())throw new ApiException(400,"NO_PARENT_MODEL","该模型没有续训前版本");
        String comparison=DatasetService.uuid();
        var child=training.start(actor,new TrainingService.Start(input.datasetId(),input.versionId(),"EVALUATE",input.preparationId(),modelId,null,"续训版本共同测试",null,null,null));
        var previous=training.start(actor,new TrainingService.Start(input.datasetId(),input.versionId(),"EVALUATE",input.preparationId(),parent,null,"父版本共同测试",null,null,null));
        String childId=child.path("runId").asText(),parentId=previous.path("runId").asText();
        for(var pair:List.of(new String[]{childId,parentId,"CHILD"},new String[]{parentId,childId,"PARENT"}))
            data.db.update("UPDATE ml_run SET options_json=JSON_SET(options_json,'$.comparisonId',?,'$.comparisonPeerId',?,'$.comparisonRole',?) WHERE id=?",comparison,pair[1],pair[2],pair[0]);
        return get(actor,childId);
    }
    Map<String,Object>[] pair(CurrentUser actor,String childId){
        var child=data.runRow(actor,childId);var options=JsonSupport.parse(data.json,child.get("options_json").toString());
        if(!"EVALUATE".equals(child.get("action"))||!"CHILD".equals(options.path("comparisonRole").asText()))throw DatasetService.missing();
        var parent=data.runRow(actor,options.path("comparisonPeerId").asText());var other=JsonSupport.parse(data.json,parent.get("options_json").toString());
        var model=training.model(actor,options.path("modelId").asText());
        if(!"PARENT".equals(other.path("comparisonRole").asText())||!childId.equals(other.path("comparisonPeerId").asText())||!options.path("comparisonId").equals(other.path("comparisonId"))||!options.path("preparationId").equals(other.path("preparationId"))||!child.get("dataset_id").equals(parent.get("dataset_id"))||!child.get("input_version_id").equals(parent.get("input_version_id"))||!other.path("modelId").asText().equals(Objects.toString(model.get("parent_model_id"),"")))throw DatasetService.missing();
        @SuppressWarnings("unchecked") Map<String,Object>[] result=new Map[]{parent,child};return result;
    }
    public JsonNode get(CurrentUser actor,String childId){
        var pair=pair(actor,childId);var parent=pair[0];var child=pair[1];var options=JsonSupport.parse(data.json,child.get("options_json").toString());
        var result=data.json.createObjectNode().put("childRunId",childId).put("parentRunId",parent.get("id").toString()).put("comparisonId",options.path("comparisonId").asText()).put("datasetId",child.get("dataset_id").toString()).put("versionId",child.get("input_version_id").toString()).put("preparationId",options.path("preparationId").asText()).put("parentStatus",parent.get("status").toString()).put("childStatus",child.get("status").toString());
        result.put("childModelId",options.path("modelId").asText()).put("parentModelId",JsonSupport.parse(data.json,parent.get("options_json").toString()).path("modelId").asText());
        if(child.get("created_at")!=null)result.put("createdAt",((java.time.LocalDateTime)child.get("created_at")).atOffset(java.time.ZoneOffset.UTC).toString());
        for(var entry:List.of(new Object[]{"parent",parent},new Object[]{"child",child})){
            @SuppressWarnings("unchecked") var row=(Map<String,Object>)entry[1];String prefix=entry[0].toString();
            result.put(prefix+"Error",Objects.toString(row.get("error_message"),""));
            if(row.get("result_json")!=null)result.set(prefix+"Metrics",JsonSupport.parse(data.json,row.get("result_json").toString()).path("metrics"));
        }
        return result;
    }
    public JsonNode list(CurrentUser actor,String modelId,int page,int size){
        training.model(actor,modelId);if(page<1||size<1||size>100)throw new ApiException(400,"VALIDATION_ERROR","分页参数无效");
        String from=" FROM ml_run WHERE action='EVALUATE' AND JSON_UNQUOTE(JSON_EXTRACT(options_json,'$.modelId'))=? AND JSON_UNQUOTE(JSON_EXTRACT(options_json,'$.comparisonRole'))='CHILD'";
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,modelId));var items=result.putArray("items");
        for(String id:data.db.queryForList("SELECT id"+from+" ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",String.class,modelId,size,(page-1L)*size))items.add(get(actor,id));return result;
    }
    public JsonNode changes(CurrentUser actor,String childId,int page,int size,String filter)throws Exception{
        if(page<1||size<1||size>100||!Set.of("errors","changed","improved","regressed").contains(filter))throw new ApiException(400,"VALIDATION_ERROR","对照筛选参数无效");
        var pair=pair(actor,childId);var parent=pair[0];var child=pair[1];
        if(!"COMPLETED".equals(parent.get("status"))||!"COMPLETED".equals(child.get("status")))throw new ApiException(409,"COMPARISON_NOT_READY","两次评价完成后可查看错误变化");
        var a=JsonSupport.parse(data.json,parent.get("result_json").toString());var b=JsonSupport.parse(data.json,child.get("result_json").toString());
        if(!a.path("preparationSha256").equals(b.path("preparationSha256")))throw new ApiException(409,"COMPARISON_DATA_CHANGED","父子评价的数据划分不一致");
        Path parentFile=training.artifact(actor,parent.get("id").toString(),"predictions.jsonl"),childFile=training.artifact(actor,childId,"predictions.jsonl");
        for(var item:List.of(Map.entry(parentFile,a),Map.entry(childFile,b))){String expected=item.getValue().path("artifacts").path("predictions.jsonl").asText();if(!expected.matches("[0-9a-f]{64}")||!TrainingAnalyticsService.hash(item.getKey()).equals(expected))throw TrainingAnalyticsService.changed();}
        var result=data.json.createObjectNode();var items=result.putArray("items");long total=0,improved=0,regressed=0,changed=0;
        try(var left=Files.newBufferedReader(parentFile);var right=Files.newBufferedReader(childFile)){
            String line;while((line=left.readLine())!=null){String other=right.readLine();if(other==null)throw new IllegalStateException("共同测试记录数量不一致");var p=data.json.readTree(line);var c=data.json.readTree(other);
                for(String key:List.of("id","sentence1","sentence2","label"))if(!p.path(key).equals(c.path(key)))throw new IllegalStateException("共同测试样本身份不一致");
                boolean goodP=p.path("predicted").asInt()==p.path("label").asInt(),goodC=c.path("predicted").asInt()==c.path("label").asInt(),different=p.path("predicted").asInt()!=c.path("predicted").asInt();
                if(!goodP&&goodC)improved++;if(goodP&&!goodC)regressed++;if(different)changed++;
                boolean include=switch(filter){case "improved"->!goodP&&goodC;case "regressed"->goodP&&!goodC;case "changed"->different;default->!goodP||!goodC;};
                if(include){if(total>=(page-1L)*size&&items.size()<size){var row=items.addObject();for(String key:List.of("id","sentence1","sentence2","label"))row.set(key,c.path(key));row.set("parentScore",p.path("score"));row.set("childScore",c.path("score"));row.set("parentPrediction",p.path("predicted"));row.set("childPrediction",c.path("predicted"));row.put("change",!goodP&&goodC?"IMPROVED":goodP&&!goodC?"REGRESSED":"BOTH_ERROR");}total++;}
            }if(right.readLine()!=null)throw new IllegalStateException("共同测试记录数量不一致");
        }
        return result.put("page",page).put("pageSize",size).put("total",total).put("improved",improved).put("regressed",regressed).put("changed",changed);
    }
}
