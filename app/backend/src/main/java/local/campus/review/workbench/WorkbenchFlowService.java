package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import org.springframework.stereotype.Service;
import java.util.*;

/** A user's saved task selection. Computation remains in the existing job services. */
@Service
public class WorkbenchFlowService {
    final DatasetService data;final TrainingService training;
    static final Set<String> KEYS=Set.of("datasetId","versionId","preparationId","trainingRunId","evaluationRunId","modelId","parentModelId","importId");
    public WorkbenchFlowService(DatasetService data,TrainingService training){this.data=data;this.training=training;}
    public record Create(String requestId,String kind,String name){}
    public record Edit(long revision,JsonNode context,String step){public Edit(long revision,JsonNode context){this(revision,context,null);}}
    private ApiException invalid(String message){return new ApiException(400,"VALIDATION_ERROR",message);}
    void access(CurrentUser user,String kind){data.role(user);if(Set.of("TRAIN","CONTINUE").contains(kind))AccessPolicy.requireAdmin(user);}
    Map<String,Object> owned(CurrentUser user,String id){
        data.role(user);DatasetService.identity(id);
        var rows=data.db.queryForList("SELECT * FROM workbench_flow WHERE id=?",id);
        if(rows.isEmpty()||!user.userId().equals(rows.getFirst().get("created_by").toString()))throw DatasetService.missing();
        access(user,rows.getFirst().get("kind").toString());return rows.getFirst();
    }
    public JsonNode create(CurrentUser user,Create input){
        data.role(user);if(input==null||input.kind()==null||!Set.of("UPLOAD","TRAIN","CONTINUE","LIBRARY").contains(input.kind()))throw invalid("请选择任务类型");
        access(user,input.kind());DatasetService.identity(input.requestId());
        String name=input.name()==null?switch(input.kind()){case "UPLOAD"->"上传数据集";case "TRAIN"->"新建模型训练";case "CONTINUE"->"继续训练已有模型";default->"加入参考库";}:DatasetService.name(input.name());
        data.db.update("INSERT IGNORE INTO workbench_flow(id,kind,name,context_json,current_step,created_by,created_at,updated_at) VALUES(?,?,?,'{}',?,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",input.requestId(),input.kind(),name,input.kind().equals("CONTINUE")?"parent":"data",user.userId());
        var row=owned(user,input.requestId());if(!input.kind().equals(row.get("kind")))throw invalid("任务类型与原请求不一致");return response(row);
    }
    public JsonNode get(CurrentUser user,String id){return response(owned(user,id));}
    public JsonNode list(CurrentUser user,int page,int size,String q){
        data.role(user);if(page<1||size<1||size>100||q.length()>120)throw invalid("列表参数无效");
        String from=" FROM workbench_flow WHERE created_by=? AND name LIKE ?"+(user.role()==CurrentUser.Role.ADMIN?"":" AND kind IN ('UPLOAD','LIBRARY')");
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,user.userId(),"%"+q+"%"));
        var items=result.putArray("items");for(var row:data.db.queryForList("SELECT *"+from+" ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",user.userId(),"%"+q+"%",size,(page-1L)*size))items.add(response(row));return result;
    }
    public JsonNode update(CurrentUser user,String id,Edit input){
        var row=owned(user,id);if(input==null||input.revision()!=((Number)row.get("revision")).longValue())throw conflict();
        var context=validateContext(user,row.get("kind").toString(),input.context());
        String step=input.step()==null?Objects.toString(row.get("current_step"),"data"):input.step();if(!Set.of("parent","data","quality","library","prepare","train","evaluate","predict").contains(step))throw invalid("任务阶段无效");
        if(data.db.update("UPDATE workbench_flow SET context_json=?,current_step=?,revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE id=? AND revision=?",context.toString(),step,id,input.revision())!=1)throw conflict();
        return get(user,id);
    }
    private ApiException conflict(){return new ApiException(409,"FLOW_CHANGED","任务已在其他页面更新，请重新打开当前任务");}
    ObjectNode validateContext(CurrentUser user,String kind,JsonNode input){
        access(user,kind);if(input==null||!input.isObject()||input.toString().length()>4000)throw invalid("任务选择无效");
        var context=data.json.createObjectNode();var fields=input.fields();while(fields.hasNext()){
            var item=fields.next();if(!KEYS.contains(item.getKey()))throw invalid("任务字段无效");
            if(item.getValue().isNull())continue;
            if(!item.getValue().isTextual())throw invalid("任务编号无效");if(item.getValue().asText().isEmpty())continue;DatasetService.identity(item.getValue().asText());context.put(item.getKey(),item.getValue().asText());
        }
        Map<String,Object> dataset=null;String datasetId=context.path("datasetId").asText(),versionId=context.path("versionId").asText();
        if(!datasetId.isEmpty())dataset=data.dataset(user,datasetId);
        if(!versionId.isEmpty()){
            if(dataset==null)throw invalid("请先选择数据集");var version=data.version(datasetId,versionId);
            if(!datasetId.equals(version.get("dataset_id").toString()))throw invalid("版本与数据集不匹配");
        }
        if(context.has("parentModelId")){
            if(!"CONTINUE".equals(kind))throw invalid("当前任务不接受起始模型");
            var parent=training.model(user,context.path("parentModelId").asText());
            if(Boolean.TRUE.equals(parent.get("archived")))throw invalid("起始模型已归档");
            if(dataset!=null&&!dataset.get("organization_id").toString().equals(parent.get("organization_id").toString()))throw invalid("模型与数据须属于同一部门");
        }
        for(String key:List.of("preparationId","trainingRunId","evaluationRunId"))if(context.has(key)){
            if(dataset==null||versionId.isEmpty())throw invalid("请先选择数据版本");var run=data.runRow(user,context.path(key).asText());
            String action=run.get("action").toString();boolean compatible=switch(key){case "preparationId"->Set.of("PREPARE","GENERATE").contains(action);case "trainingRunId"->"TRAIN".equals(action);default->"EVALUATE".equals(action);};
            if(!compatible||!"evaluationRunId".equals(key)&&(!datasetId.equals(run.get("dataset_id").toString())||!versionId.equals(run.get("input_version_id").toString())))throw invalid("运行任务与所选数据版本不匹配");
            if("evaluationRunId".equals(key))data.dataset(user,run.get("dataset_id").toString());
            if("evaluationRunId".equals(key)&&!context.path("modelId").asText().equals(JsonSupport.parse(data.json,run.get("options_json").toString()).path("modelId").asText()))throw invalid("评价与当前模型不匹配");
        }
        if(context.has("modelId")){
            if(dataset==null||versionId.isEmpty()||!context.has("trainingRunId"))throw invalid("请关联本次模型的训练记录");
            var model=training.model(user,context.path("modelId").asText());var run=data.runRow(user,model.get("run_id").toString());
            if(!context.path("trainingRunId").asText().equals(model.get("run_id").toString())||!datasetId.equals(model.get("dataset_id").toString())||!versionId.equals(run.get("input_version_id").toString()))throw invalid("模型与当前训练不匹配");
        }
        if(context.has("importId")){
            if(dataset==null||!"NEWS".equals(dataset.get("kind")))throw invalid("请选择新闻数据集");
            var rows=data.db.queryForList("SELECT dataset_id,version_id FROM reference_import WHERE id=?",context.path("importId").asText());
            if(rows.isEmpty()||!datasetId.equals(rows.getFirst().get("dataset_id").toString())||!versionId.equals(rows.getFirst().get("version_id").toString()))throw invalid("入库批次与数据版本不匹配");
        }
        return context;
    }
    private JsonNode response(Map<String,Object> row){
        var result=data.json.createObjectNode().put("flowId",row.get("id").toString()).put("kind",row.get("kind").toString()).put("name",row.get("name").toString()).put("revision",((Number)row.get("revision")).longValue());
        result.put("currentStep",Objects.toString(row.get("current_step"),"data"));
        result.set("context",JsonSupport.parse(data.json,row.get("context_json").toString()));for(String key:List.of("created_at","updated_at"))result.put(key.equals("created_at")?"createdAt":"updatedAt",Objects.toString(row.get(key),""));return result;
    }
}
