package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import java.util.*;
import java.nio.file.Files;

/** Durable dispatcher: each child claim and state update commit together. */
@Service
public class AutomaticPipelineService {
    private final DatasetService data;private final TrainingService training;private final CurrentUserService users;private final boolean enabled;private volatile boolean ready;
    public AutomaticPipelineService(DatasetService data,TrainingService training,CurrentUserService users,@Value("${campus.workbench.enabled:true}")boolean enabled){this.data=data;this.training=training;this.users=users;this.enabled=enabled;}
    public record Model(String family,JsonNode parameters){}
    public record Create(String datasetId,String versionId,String name,JsonNode mapping,JsonNode cleaning,JsonNode preparation,JsonNode generation,List<Model> models,boolean evaluate){}
    public JsonNode create(CurrentUser actor,Create input){
        data.role(actor);if(input==null)throw invalid("请配置自动流程");var dataset=data.dataset(actor,input.datasetId());var version=data.version(input.datasetId(),input.versionId());
        if(Boolean.TRUE.equals(dataset.get("archived"))||!"READY".equals(version.get("status"))||"sources.json".equals(version.get("file_name")))throw invalid("请选择未归档数据集的就绪数据版本");
        validateModels(input.models());String name=DatasetService.name(input.name());
        var config=data.json.createObjectNode().put("inputSha256",version.get("sha256").toString()).put("kind",dataset.get("kind").toString()).put("evaluate",input.evaluate());
        for(var entry:Map.of("mapping",node(input.mapping()),"cleaning",node(input.cleaning()),"preparation",node(input.preparation()),"generation",node(input.generation())).entrySet()){
            if(!entry.getValue().isObject()||entry.getValue().toString().length()>10000)throw invalid("流程参数格式无效");config.set(entry.getKey(),entry.getValue());
        }
        var models=config.putArray("models");for(var model:input.models())models.addObject().put("family",model.family()).set("parameters",training.parameters(model.family(),model.parameters()));
        var state=initial(data.json,"RAW".equals(version.get("stage")),input.versionId());String id=DatasetService.uuid();
        data.transactions.executeWithoutResult(tx->{
            if(Boolean.TRUE.equals(data.db.queryForObject("SELECT archived FROM ml_dataset WHERE id=? FOR UPDATE",Boolean.class,input.datasetId())))throw invalid("数据集已归档");
            data.db.update("INSERT INTO ml_pipeline(id,dataset_id,input_version_id,name,status,config_json,state_json,created_by,actor_id,created_at,updated_at) VALUES(?,?,?,?,'QUEUED',?,?,?,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",id,input.datasetId(),input.versionId(),name,config.toString(),state.toString(),actor.userId(),actor.userId());
        });return data.json.createObjectNode().put("pipelineId",id);
    }
    private JsonNode node(JsonNode value){return value==null?data.json.createObjectNode():value;}
    static void validateModels(List<Model> models){if(models==null||models.isEmpty()||models.size()>6)throw invalid("请选择1—6个模型");var families=new HashSet<String>();for(var model:models)if(model==null||model.family()==null||!TrainingService.FAMILIES.contains(model.family())||!families.add(model.family()))throw invalid("模型无效或重复");}
    static ApiException invalid(String message){return new ApiException(400,"VALIDATION_ERROR",message);}
    static ObjectNode initial(ObjectMapper json,boolean raw,String version){var state=json.createObjectNode().put("stage",raw?"CLEAN":"PREPARE").put("modelIndex",0);state.putArray("steps");state.putArray("models");if(!raw)state.put("cleanVersionId",version);return state;}
    private Map<String,Object> row(CurrentUser actor,String id){data.role(actor);DatasetService.identity(id);var rows=data.db.queryForList("SELECT * FROM ml_pipeline WHERE id=?",id);if(rows.isEmpty())throw DatasetService.missing();data.dataset(actor,rows.getFirst().get("dataset_id").toString());return rows.getFirst();}
    public JsonNode get(CurrentUser actor,String id){return view(row(actor,id));}
    private ObjectNode view(Map<String,Object> row){var result=data.json.createObjectNode().put("pipelineId",row.get("id").toString()).put("datasetId",row.get("dataset_id").toString()).put("name",row.get("name").toString()).put("status",row.get("status").toString()).put("error",Objects.toString(row.get("error_message"),"")).put("updatedAt",row.get("updated_at").toString());var state=(ObjectNode)JsonSupport.parse(data.json,row.get("state_json").toString());
        for(var step:state.withArray("steps")){var jobs=data.db.queryForList("SELECT status,error_message FROM ml_run WHERE id=?",step.path("runId").asText());if(!jobs.isEmpty())((ObjectNode)step).put("status",jobs.getFirst().get("status").toString()).put("error",Objects.toString(jobs.getFirst().get("error_message"),""));}
        result.set("state",state);return result;
    }
    public JsonNode list(CurrentUser actor,String dataset,int page){data.dataset(actor,dataset);if(page<1)throw invalid("分页无效");var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*) FROM ml_pipeline WHERE dataset_id=?",Long.class,dataset));var items=result.putArray("items");for(var row:data.db.queryForList("SELECT * FROM ml_pipeline WHERE dataset_id=? ORDER BY created_at DESC,id LIMIT 10 OFFSET ?",dataset,(page-1L)*10))items.add(view(row));return result;}
    public JsonNode control(CurrentUser actor,String id,boolean retry){row(actor,id);data.transactions.executeWithoutResult(tx->{
        var current=data.db.queryForMap("SELECT * FROM ml_pipeline WHERE id=? FOR UPDATE",id);var state=(ObjectNode)JsonSupport.parse(data.json,current.get("state_json").toString());String status=current.get("status").toString();
        if(retry){if(!Set.of("FAILED","CANCELLED").contains(status))throw invalid("仅失败或已取消流程可重试");if(state.hasNonNull("currentRunId")&&!"COMPLETED".equals(data.runRow(actor,state.path("currentRunId").asText()).get("status"))){state.put("retryRunId",state.path("currentRunId").asText());state.remove("currentRunId");}data.db.update("UPDATE ml_pipeline SET status='QUEUED',state_json=?,error_message=NULL,actor_id=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?",state.toString(),actor.userId(),id);}
        else {if(Set.of("QUEUED","RUNNING").contains(status)&&state.hasNonNull("currentRunId"))data.cancel(actor,state.path("currentRunId").asText());data.db.update("UPDATE ml_pipeline SET status=CASE WHEN status IN ('QUEUED','RUNNING') THEN 'CANCELLED' ELSE status END,updated_at=UTC_TIMESTAMP(3) WHERE id=?",id);}
    });return get(actor,id);}
    @EventListener(ApplicationReadyEvent.class) public void ready(){ready=true;}
    @Scheduled(fixedDelay=1500) public void poll(){if(!enabled||!ready)return;for(String id:data.db.queryForList("SELECT id FROM ml_pipeline WHERE status IN ('QUEUED','RUNNING') ORDER BY created_at LIMIT 20",String.class))advance(id);}
    void advance(String id){
        try{data.transactions.executeWithoutResult(tx->{
            var row=data.db.queryForMap("SELECT * FROM ml_pipeline WHERE id=? FOR UPDATE",id);if(!Set.of("QUEUED","RUNNING").contains(row.get("status")))return;
            String username=data.db.queryForObject("SELECT username FROM app_user WHERE id=?",String.class,row.get("actor_id"));var actor=users.require(UsernamePasswordAuthenticationToken.authenticated(username,null,List.of()));
            String dataset=row.get("dataset_id").toString();data.dataset(actor,dataset);
            var config=JsonSupport.parse(data.json,row.get("config_json").toString());var state=(ObjectNode)JsonSupport.parse(data.json,row.get("state_json").toString());
            if(!config.path("inputSha256").asText().equals(data.version(dataset,row.get("input_version_id").toString()).get("sha256")))throw invalid("流程输入版本已变化");
            if(state.hasNonNull("currentRunId")){
                var child=data.runRow(actor,state.path("currentRunId").asText());String childStatus=child.get("status").toString();if(!DatasetService.TERMINAL.contains(childStatus))return;
                if(!"COMPLETED".equals(childStatus)){data.db.update("UPDATE ml_pipeline SET status=?,error_message=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?","CANCELLED".equals(childStatus)?"CANCELLED":"FAILED",Objects.toString(child.get("error_message"),"阶段未完成"),id);return;}
                var result=JsonSupport.parse(data.json,child.get("result_json").toString());consume(state,config,result,child);
                if("BLOCKED".equals(state.path("stage").asText())){data.db.update("UPDATE ml_pipeline SET status='BLOCKED',state_json=?,error_message='样本划分缺少可训练标签或类别，请补充材料后新建流程',updated_at=UTC_TIMESTAMP(3) WHERE id=?",state.toString(),id);return;}
            }
            if("DONE".equals(state.path("stage").asText())){data.db.update("UPDATE ml_pipeline SET status='COMPLETED',state_json=?,error_message=NULL,updated_at=UTC_TIMESTAMP(3) WHERE id=?",state.toString(),id);return;}
            String stage=state.path("stage").asText(),version=state.path("cleanVersionId").asText(),preparation=state.path("preparationId").asText(null),resume=null;JsonNode started;int index=state.path("modelIndex").asInt();var model=config.path("models").get(index);
            if(state.hasNonNull("retryRunId")&&Set.of("GENERATE","TRAIN").contains(stage)){
                var previous=data.runRow(actor,state.path("retryRunId").asText());if((stage.equals("GENERATE")&&Files.isRegularFile(training.directory(previous.get("id").toString()).resolve("generation.sqlite")))||(stage.equals("TRAIN")&&TrainingCheckpoints.inspect(data,previous).path("available").asBoolean()))resume=state.path("retryRunId").asText();
            }
            String childName=row.get("name").toString();childName=childName.substring(0,Math.min(80,childName.length()))+" · "+stage;
            if(stage.equals("CLEAN"))started=data.start(actor,dataset,row.get("input_version_id").toString(),"CLEAN",config.path("mapping"),config.path("cleaning"));
            else {
                String family=stage.equals("TRAIN")?model.path("family").asText():null,modelId=stage.equals("EVALUATE")?state.path("latestModelId").asText():null;
                JsonNode parameters=stage.equals("PREPARE")?config.path("preparation"):stage.equals("GENERATE")?config.path("generation"):stage.equals("TRAIN")?model.path("parameters"):null;
                if(stage.equals("GENERATE"))preparation=state.path("groupingRunId").asText();
                started=training.start(actor,new TrainingService.Start(dataset,version,stage,preparation,modelId,family,childName,parameters,null,resume));
            }
            String run=started.path("runId").asText();state.put("currentRunId",run);state.remove("retryRunId");state.withArray("steps").addObject().put("stage",stage).put("runId",run).put("family",stage.equals("TRAIN")||stage.equals("EVALUATE")?model.path("family").asText():"");
            data.db.update("UPDATE ml_pipeline SET status='RUNNING',state_json=?,error_message=NULL,updated_at=UTC_TIMESTAMP(3) WHERE id=?",state.toString(),id);
        });}catch(Exception error){String message=Objects.toString(error.getMessage(),"流程阶段派发失败");if(message.length()>900)message=message.substring(0,900);data.db.update("UPDATE ml_pipeline SET status='FAILED',error_message=?,updated_at=UTC_TIMESTAMP(3) WHERE id=? AND status IN ('QUEUED','RUNNING')",message,id);}
    }
    static void consume(ObjectNode state,JsonNode config,JsonNode result,Map<String,Object> child){
        String stage=state.path("stage").asText(),run=child.get("id").toString();state.remove("currentRunId");
        switch(stage){
            case "CLEAN"->{state.put("cleanVersionId",child.get("output_version_id").toString()).put("stage","PREPARE");}
            case "PREPARE"->{if("NEWS".equals(config.path("kind").asText()))state.put("groupingRunId",run).put("stage","GENERATE");else state.put("preparationId",run).put("stage",result.path("trainReady").asBoolean()?"TRAIN":"BLOCKED");}
            case "GENERATE"->state.put("preparationId",run).put("stage",result.path("trainReady").asBoolean()?"TRAIN":"BLOCKED");
            case "TRAIN"->{state.put("latestModelId",run);state.withArray("models").addObject().put("family",config.path("models").get(state.path("modelIndex").asInt()).path("family").asText()).put("modelId",run);if(config.path("evaluate").asBoolean())state.put("stage","EVALUATE");else nextModel(state,config);}
            case "EVALUATE"->{((ObjectNode)state.withArray("models").get(state.withArray("models").size()-1)).put("evaluationRunId",run);nextModel(state,config);}
            default->throw invalid("流程阶段无效");
        }
    }
    private static void nextModel(ObjectNode state,JsonNode config){int index=state.path("modelIndex").asInt()+1;state.put("modelIndex",index).put("stage",index>=config.path("models").size()?"DONE":"TRAIN");}
}
