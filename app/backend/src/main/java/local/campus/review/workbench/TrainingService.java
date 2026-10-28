package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.util.*;

/** Experiments consume immutable data versions and never change production models. */
@Service
public class TrainingService {
    static final Set<String> ACTIONS=Set.of("PREPARE","GENERATE","TRAIN","EVALUATE","PREDICT");
    static final Set<String> FAMILIES=Set.of("lr","svm","rf","cnn","bilstm","bert");
    final DatasetService data;
    public TrainingService(DatasetService data){this.data=data;}
    Path directory(String run){DatasetService.identity(run);return data.settings.runtime().resolve("workbench/computations").resolve(run);}
    private ApiException invalid(String text){return new ApiException(400,"VALIDATION_ERROR",text);}
    ObjectNode parameters(String family,JsonNode input){
        if(!FAMILIES.contains(family))throw invalid("请选择支持的训练模型");
        if(input==null)input=data.json.createObjectNode();if(!input.isObject())throw invalid("训练参数格式无效");
        var limits=Map.ofEntries(Map.entry("seed",new double[]{0,2147483647}),Map.entry("C",new double[]{.0001,10000}),Map.entry("max_iter",new double[]{10,20000}),Map.entry("n_estimators",new double[]{10,1000}),Map.entry("max_depth",new double[]{1,100}),Map.entry("min_samples_leaf",new double[]{1,100}),Map.entry("epochs",new double[]{1,30}),Map.entry("batch_size",new double[]{1,256}),Map.entry("learning_rate",new double[]{.0000001,.1}),Map.entry("width",new double[]{16,256}),Map.entry("dropout",new double[]{0,.8}),Map.entry("max_length",new double[]{8,512}),Map.entry("patience",new double[]{0,30}),Map.entry("weight_decay",new double[]{0,1}),Map.entry("gradient_accumulation",new double[]{1,32}));
        var floats=Set.of("C","learning_rate","dropout","weight_decay");
        var fields=input.fields();while(fields.hasNext()){
            var entry=fields.next();String key=entry.getKey();var value=entry.getValue();
            if(key.equals("device")){if(!Set.of("cpu","cuda").contains(value.asText()))throw invalid("设备无效");continue;}
            if(key.equals("class_weight")){if(!Set.of("none","balanced").contains(value.asText()))throw invalid("类别权重无效");continue;}
            var bound=limits.get(key);
            if(bound==null || !value.isNumber() || (!floats.contains(key) && !value.isIntegralNumber()) || !Double.isFinite(value.asDouble()) || value.asDouble()<bound[0] || value.asDouble()>bound[1])throw invalid("训练参数超出范围："+key);
        }
        return (ObjectNode)input.deepCopy();
    }
    Map<String,Object> model(CurrentUser user,String id){
        data.role(user);DatasetService.identity(id);var rows=data.db.queryForList("SELECT * FROM ml_model WHERE id=?",id);
        if(rows.isEmpty())throw DatasetService.missing();var model=rows.getFirst();data.organization(user,model.get("organization_id").toString());return model;
    }
    Map<String,Object> preparation(CurrentUser user,String id,String dataset){
        var run=data.runRow(user,id);
        if(!Set.of("PREPARE","GENERATE").contains(run.get("action")) || !"COMPLETED".equals(run.get("status")) || !dataset.equals(run.get("dataset_id")))throw invalid("请选择当前数据集已完成的样本划分");
        return run;
    }
    public record Start(String datasetId,String versionId,String action,String preparationId,String modelId,String family,String name,JsonNode parameters,JsonNode rows,String resumeRunId){}
    public JsonNode start(CurrentUser user,Start request){
        if(request.action()==null || !ACTIONS.contains(request.action()))throw invalid("任务类型无效");
        var dataset=data.dataset(user,request.datasetId());var version=data.version(request.datasetId(),request.versionId());
        if(!"CLEAN".equals(version.get("stage")) || !"READY".equals(version.get("status")))throw invalid("请选择已完成的清洗版本");
        var options=data.json.createObjectNode().put("name",DatasetService.name(request.name()==null?dataset.get("name").toString():request.name()));
        switch(request.action()){
            case "PREPARE" -> {
                var config=request.parameters()==null?data.json.createObjectNode():request.parameters();
                if(!config.isObject() || config.toString().length()>1000)throw invalid("划分参数无效");
                config.fieldNames().forEachRemaining(key->{if(!Set.of("ratios","seed").contains(key))throw invalid("划分参数无效");});
                if(config.has("seed") && (!config.get("seed").isIntegralNumber() || config.get("seed").asLong()<0 || config.get("seed").asLong()>2147483647))throw invalid("随机种子无效");
                if(config.has("ratios")){
                    var ratios=config.get("ratios");double sum=0;if(!ratios.isArray() || ratios.size()!=3)throw invalid("请设置训练、验证、测试比例");
                    for(var ratio:ratios){if(!ratio.isNumber() || !Double.isFinite(ratio.asDouble()) || ratio.asDouble()<.01 || ratio.asDouble()>.98)throw invalid("划分比例无效");sum+=ratio.asDouble();}
                    if(Math.abs(sum-1)>.00001)throw invalid("划分比例合计须为1");
                }
                options.set("parameters",config);
            }
            case "GENERATE" -> {
                var prepared=preparation(user,request.preparationId(),request.datasetId());
                if(!"NEWS".equals(dataset.get("kind")) || !"PREPARE".equals(prepared.get("action")) || !request.versionId().equals(prepared.get("input_version_id")))throw invalid("请选择当前原稿版本的新闻分组");
                var config=request.parameters()==null?data.json.createObjectNode():request.parameters();
                if(!config.isObject())throw invalid("样本生成参数无效");
                var bounds=Map.of("max_originals",new int[]{0,100000},"segment_characters",new int[]{128,512},"min_characters",new int[]{32,256},"variants",new int[]{1,4},"negative_candidates",new int[]{5,200},"negatives_per_positive",new int[]{1,4},"attempts",new int[]{1,4},"seed",new int[]{0,2147483647});
                var fields=config.fields();while(fields.hasNext()){
                    var field=fields.next();String key=field.getKey();var value=field.getValue();
                    if(key.equals("device")){if(!Set.of("cpu","cuda").contains(value.asText()))throw invalid("设备无效");continue;}
                    if(key.equals("reuse_existing")){if(!value.isBoolean())throw invalid("复用选项无效");continue;}
                    var range=bounds.get(key);if(range==null || !value.isIntegralNumber() || value.asLong()<range[0] || value.asLong()>range[1])throw invalid("样本参数超出范围："+key);
                }
                options.put("preparationId",request.preparationId());options.set("parameters",config);
                if(request.resumeRunId()!=null){
                    var previous=data.runRow(user,request.resumeRunId());
                    if(!"GENERATE".equals(previous.get("action")) || !DatasetService.TERMINAL.contains(previous.get("status")) || !request.datasetId().equals(previous.get("dataset_id")) || !request.versionId().equals(previous.get("input_version_id")) || !Files.isRegularFile(directory(request.resumeRunId()).resolve("generation.sqlite")))throw invalid("没有可继续的样本检查点");
                    options.put("resumeRunId",request.resumeRunId());
                }
            }
            case "TRAIN","EVALUATE" -> {
                var prepared=preparation(user,request.preparationId(),request.datasetId());
                if(!request.versionId().equals(prepared.get("input_version_id")))throw invalid("样本划分与清洗版本不一致");
                var result=JsonSupport.parse(data.json,prepared.get("result_json").toString());
                if(!result.path("trainReady").asBoolean())throw invalid("样本尚缺标签或部分类别，请补充标签句对");
                options.put("preparationId",request.preparationId());
                if(request.action().equals("TRAIN")){
                    if(request.family()==null)throw invalid("请选择模型");
                    options.put("family",request.family());options.set("parameters",parameters(request.family(),request.parameters()));
                }else bindModel(user,request.modelId(),dataset,options);
            }
            case "PREDICT" -> {
                bindModel(user,request.modelId(),dataset,options);
                if(request.rows()!=null){
                    if(!request.rows().isArray() || request.rows().isEmpty() || request.rows().size()>100 || request.rows().toString().length()>500000)throw invalid("单次输入最多100个句对");
                    for(var row:request.rows())for(String field:List.of("sentence1","sentence2"))if(!row.path(field).isTextual() || row.path(field).asText().isBlank() || row.path(field).asText().length()>20000)throw invalid("请填写有效的两个文本，单段最多20000字");
                    options.set("rows",request.rows());
                }else if(request.preparationId()!=null){
                    var prepared=preparation(user,request.preparationId(),request.datasetId());
                    if(!request.versionId().equals(prepared.get("input_version_id")) || !JsonSupport.parse(data.json,prepared.get("result_json").toString()).path("trainReady").asBoolean())throw invalid("请选择可用的句对样本版本");
                    options.put("preparationId",request.preparationId());
                }else if(!"PAIRS".equals(dataset.get("kind")))throw invalid("批量预测请选择标签句对或已生成的样本版本");
            }
        }
        String id=DatasetService.uuid();
        data.transactions.executeWithoutResult(tx->{
            if(Boolean.TRUE.equals(data.db.queryForObject("SELECT archived FROM ml_dataset WHERE id=? FOR UPDATE",Boolean.class,request.datasetId())))throw new ApiException(409,"DATASET_ARCHIVED","请先恢复数据集");
            data.insertRun(id,request.datasetId(),request.versionId(),null,request.action(),"{}",options.toString(),user.userId());
        });return data.json.createObjectNode().put("runId",id);
    }
    void bindModel(CurrentUser user,String id,Map<String,Object> dataset,ObjectNode options){
        var model=model(user,id);
        if(Boolean.TRUE.equals(model.get("archived")))throw invalid("请先恢复模型");
        if(!model.get("organization_id").toString().equals(dataset.get("organization_id").toString()))throw invalid("请选择同一部门的模型和数据");
        options.put("modelId",id);
    }
    public JsonNode runs(CurrentUser user,int page,String q){
        data.role(user);if(page<1 || q.length()>120)throw invalid("查询参数无效");
        String from=" FROM ml_run r JOIN ml_dataset d ON d.id=r.dataset_id WHERE r.action IN ('PREPARE','GENERATE','TRAIN','EVALUATE','PREDICT') AND d.name LIKE ?";
        var args=new ArrayList<Object>(List.of("%"+q+"%"));
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray()));
        args.add((page-1L)*20);var items=result.putArray("items");
        for(var row:data.db.queryForList("SELECT r.*,d.name AS dataset_name"+from+" ORDER BY r.created_at DESC,r.id LIMIT 20 OFFSET ?",args.toArray())){var item=(ObjectNode)data.runJson(row);item.put("datasetName",row.get("dataset_name").toString());items.add(item);}
        return result;
    }
    public JsonNode models(CurrentUser user,int page,String q,boolean archived){
        data.role(user);if(page<1 || q.length()>120)throw invalid("查询参数无效");
        String from=" FROM ml_model m WHERE m.archived=? AND m.name LIKE ?";var args=new ArrayList<Object>(List.of(archived,"%"+q+"%"));
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray()));args.add((page-1L)*20);var items=result.putArray("items");
        for(var row:data.db.queryForList("SELECT m.*"+from+" ORDER BY m.created_at DESC,m.id LIMIT 20 OFFSET ?",args.toArray()))items.add(modelJson(row));return result;
    }
    ObjectNode modelJson(Map<String,Object> row){
        var result=data.json.createObjectNode().put("modelId",row.get("id").toString()).put("datasetId",row.get("dataset_id").toString()).put("runId",row.get("run_id").toString()).put("name",row.get("name").toString()).put("family",row.get("family").toString()).put("organizationId",row.get("organization_id").toString()).put("archived",Boolean.TRUE.equals(row.get("archived"))).put("createdAt",row.get("created_at").toString());
        result.set("manifest",JsonSupport.parse(data.json,row.get("manifest_json").toString()));return result;
    }
    public JsonNode updateModel(CurrentUser user,String id,String name,Boolean archived){
        model(user,id);if(name==null && archived==null)throw invalid("请填写修改内容");String label=name==null?null:DatasetService.name(name);
        data.transactions.executeWithoutResult(tx->{data.db.queryForObject("SELECT id FROM ml_model WHERE id=? FOR UPDATE",String.class,id);if(Boolean.TRUE.equals(archived)&&data.db.queryForObject("SELECT COUNT(*) FROM model_release_pointer p JOIN model_release r ON r.id=p.release_id WHERE r.model_id=?",Integer.class,id)>0)throw new ApiException(409,"MODEL_IN_USE","该模型正在发布使用，请先回退或撤销发布");if(label!=null)data.db.update("UPDATE ml_model SET name=? WHERE id=?",label,id);if(archived!=null)data.db.update("UPDATE ml_model SET archived=? WHERE id=?",archived,id);});return modelJson(model(user,id));
    }
    public Path artifact(CurrentUser user,String run,String name){
        var task=data.runRow(user,run);
        if(!ACTIONS.contains(task.get("action")) || !"COMPLETED".equals(task.get("status")) || !Set.of("manifest.json","history.json","train.jsonl","validation.jsonl","test.jsonl","calibration.jsonl","segments.jsonl","predictions.jsonl","pairs.jsonl","quarantine.jsonl").contains(name))throw DatasetService.missing();
        var path=directory(run).resolve("output").resolve(name);if(!Files.isRegularFile(path))throw DatasetService.missing();return path;
    }
    public JsonNode samples(CurrentUser user,String id,String kind,int page,int size)throws Exception{
        if(page<1 || size<1 || size>100 || !Set.of("pairs","quarantine").contains(kind))throw invalid("样本分页参数无效");
        Path file=artifact(user,id,kind+".jsonl");var result=data.json.createObjectNode().put("page",page);var items=result.putArray("items");
        long total=0;try(var reader=Files.newBufferedReader(file)){String line;long begin=(long)(page-1)*size;while((line=reader.readLine())!=null){if(total>=begin && items.size()<size)items.add(data.json.readTree(line));total++;}}
        result.put("total",total);return result;
    }
}
