package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.CurrentUser;
import local.campus.review.auth.AccessPolicy;
import local.campus.review.common.*;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Experiments consume immutable data versions and never change production models. */
@Service
public class TrainingService {
    static final Set<String> ACTIONS=Set.of("PREPARE","GENERATE","TRAIN","EVALUATE","PREDICT");
    static final Set<String> TRAINING_ACTIONS=Set.of("PREPARE","GENERATE","TRAIN");
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
    public record Start(String datasetId,String versionId,String action,String preparationId,String modelId,String family,String name,JsonNode parameters,JsonNode rows,String resumeRunId,String parentModelId){
        public Start(String datasetId,String versionId,String action,String preparationId,String modelId,String family,String name,JsonNode parameters,JsonNode rows,String resumeRunId){this(datasetId,versionId,action,preparationId,modelId,family,name,parameters,rows,resumeRunId,null);}
    }
    static void requireTrainingAccess(CurrentUser user,String action){if(action!=null&&TRAINING_ACTIONS.contains(action))AccessPolicy.requireAdmin(user);}
    public JsonNode start(CurrentUser user,Start request){
        data.role(user);requireTrainingAccess(user,request.action());
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
                    if(request.parentModelId()!=null){
                        if(request.resumeRunId()!=null)throw invalid("断点恢复与继续训练须分别选择");
                        var parent=model(user,request.parentModelId());
                        if(Boolean.TRUE.equals(parent.get("archived"))||!request.family().equals(parent.get("family"))||!dataset.get("organization_id").toString().equals(parent.get("organization_id").toString()))throw invalid("起始模型与算法或部门不匹配");
                        var parentRun=data.runRow(user,parent.get("run_id").toString());
                        if(!"COMPLETED".equals(parentRun.get("status")))throw invalid("请选择已完成模型");
                        var parentOptions=JsonSupport.parse(data.json,parentRun.get("options_json").toString());
                        options.put("parentModelId",request.parentModelId()).put("parentPreparationId",parentOptions.path("preparationId").asText());
                        options.put("parentManifestSha256",modelManifestHash(parent.get("run_id").toString()));
                        options.put("trainingMode",Set.of("cnn","bilstm","bert").contains(request.family())?"CONTINUE":"REFIT");
                    }
                    if(request.resumeRunId()!=null){
                        var previous=data.runRow(user,request.resumeRunId());var saved=JsonSupport.parse(data.json,previous.get("options_json").toString());
                        if(!request.datasetId().equals(previous.get("dataset_id"))||!request.versionId().equals(previous.get("input_version_id"))||!saved.path("family").equals(options.path("family"))||!saved.path("parameters").equals(options.path("parameters"))||!saved.path("preparationId").asText().equals(request.preparationId()))throw invalid("续训须使用原数据、划分、模型及参数");
                        var checkpoint=TrainingCheckpoints.inspect(data,previous);if(!checkpoint.path("available").asBoolean())throw invalid("该运行没有可核验的续训检查点，请复制参数新建训练");
                        options.put("resumeRunId",request.resumeRunId()).put("resumeMetadataSha256",checkpoint.path("metadataSha256").asText());
                        for(String key:List.of("parentModelId","parentPreparationId","parentManifestSha256","trainingMode"))if(saved.has(key))options.set(key,saved.get(key));
                    }
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
    String modelManifestHash(String run){try{return ReleaseService.sha(directory(run).resolve("output/manifest.json"));}catch(Exception e){throw invalid("起始模型工件不可读取");}}
    void bindModel(CurrentUser user,String id,Map<String,Object> dataset,ObjectNode options){
        var model=model(user,id);
        if(Boolean.TRUE.equals(model.get("archived")))throw invalid("请先恢复模型");
        if(!model.get("organization_id").toString().equals(dataset.get("organization_id").toString()))throw invalid("请选择同一部门的模型和数据");
        options.put("modelId",id);
    }
    public JsonNode runs(CurrentUser user,int page,String q){return runs(user,page,q,null);}
    public JsonNode runs(CurrentUser user,int page,String q,String modelId){return runs(user,page,20,q,modelId);}
    public JsonNode runs(CurrentUser user,int page,int size,String q,String modelId){
        data.role(user);if(page<1 || size<1 || size>100 || q.length()>120)throw invalid("查询参数无效");
        String from=" FROM ml_run r JOIN ml_dataset d ON d.id=r.dataset_id WHERE r.action IN ('PREPARE','GENERATE','TRAIN','EVALUATE','PREDICT') AND d.name LIKE ?";
        var args=new ArrayList<Object>(List.of("%"+q+"%"));
        if(modelId!=null&&!modelId.isBlank()){
            var selected=model(user,modelId);from+=" AND (JSON_UNQUOTE(JSON_EXTRACT(r.options_json,'$.modelId'))=? OR r.id=?)";
            args.add(modelId);args.add(selected.get("run_id").toString());
        }
        var result=data.json.createObjectNode().put("page",page).put("pageSize",size).put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray()));
        args.add(size);args.add((page-1L)*size);var items=result.putArray("items");
        for(var row:data.db.queryForList("SELECT r.*,d.name AS dataset_name"+from+" ORDER BY r.created_at DESC,r.id LIMIT ? OFFSET ?",args.toArray())){var item=(ObjectNode)data.runJson(row);item.put("datasetName",row.get("dataset_name").toString());item.set("checkpoint",TrainingCheckpoints.inspect(data,row));items.add(item);}
        return result;
    }
    public JsonNode models(CurrentUser user,int page,String q,boolean archived){return models(user,page,20,q,archived);}
    public JsonNode models(CurrentUser user,int page,int size,String q,boolean archived){
        data.role(user);if(page<1 || size<1 || size>100 || q.length()>120)throw invalid("查询参数无效");
        String from=" FROM ml_model m JOIN ml_dataset d ON d.id=m.dataset_id JOIN ml_run r ON r.id=m.run_id WHERE m.archived=? AND m.name LIKE ?";var args=new ArrayList<Object>(List.of(archived,"%"+q+"%"));
        var result=data.json.createObjectNode().put("page",page).put("pageSize",size).put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray()));args.add(size);args.add((page-1L)*size);var items=result.putArray("items");
        for(var row:data.db.queryForList("SELECT m.*,d.name AS dataset_name,r.input_version_id"+from+" ORDER BY m.created_at DESC,m.id LIMIT ? OFFSET ?",args.toArray()))items.add(modelJson(row));return result;
    }
    public JsonNode modelGroups(CurrentUser user,int page,int size,String q,boolean archived){
        data.role(user);if(page<1||size<1||size>100||q.length()>120)throw invalid("查询参数无效");
        String from=" FROM ml_model m JOIN ml_model root ON root.id=m.logical_model_id JOIN ml_dataset d ON d.id=m.dataset_id JOIN ml_run r ON r.id=m.run_id WHERE m.archived=? AND (m.name LIKE ? OR root.name LIKE ?) AND m.version_number=(SELECT MAX(x.version_number) FROM ml_model x WHERE x.logical_model_id=m.logical_model_id AND x.archived=?)";
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,archived,"%"+q+"%","%"+q+"%",archived));
        var items=result.putArray("items");for(var row:data.db.queryForList("SELECT m.*,root.name AS logical_name,d.name AS dataset_name,r.input_version_id,(SELECT COUNT(*) FROM ml_model v WHERE v.logical_model_id=m.logical_model_id) AS version_count"+from+" ORDER BY m.created_at DESC,m.id LIMIT ? OFFSET ?",archived,"%"+q+"%","%"+q+"%",archived,size,(page-1L)*size))items.add(modelJson(row).put("logicalName",row.get("logical_name").toString()).put("versionCount",((Number)row.get("version_count")).intValue()));return result;
    }
    public JsonNode modelVersions(CurrentUser user,String id,int page,int size){
        var selected=model(user,id);if(page<1||size<1||size>100)throw invalid("分页无效");String logical=selected.get("logical_model_id").toString();
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*) FROM ml_model WHERE logical_model_id=?",Long.class,logical));var items=result.putArray("items");
        for(var row:data.db.queryForList("SELECT m.*,r.input_version_id FROM ml_model m JOIN ml_run r ON r.id=m.run_id WHERE m.logical_model_id=? ORDER BY m.version_number DESC LIMIT ? OFFSET ?",logical,size,(page-1L)*size))items.add(modelJson(row));return result;
    }
    public JsonNode getModel(CurrentUser user,String id){var row=model(user,id);row.put("input_version_id",data.db.queryForObject("SELECT input_version_id FROM ml_run WHERE id=?",String.class,row.get("run_id")));var result=modelJson(row);var bundles=data.db.queryForList("SELECT id FROM ml_pipeline WHERE bundle_version=1 AND JSON_SEARCH(state_json,'one',?,NULL,'$.models[*].modelId') IS NOT NULL ORDER BY created_at DESC LIMIT 1",String.class,id);if(!bundles.isEmpty())result.put("bundleId",bundles.getFirst());return result;}
    public JsonNode experiments(CurrentUser user,String id,int page,int size){
        var selected=model(user,id);if(page<1||size<1||size>100)throw invalid("分页参数无效");
        String from=" FROM ml_model m JOIN ml_run r ON r.id=m.run_id JOIN ml_dataset d ON d.id=m.dataset_id WHERE m.organization_id=? AND m.family=? AND m.archived=FALSE";
        var result=data.json.createObjectNode().put("total",data.db.queryForObject("SELECT COUNT(*)"+from,Long.class,selected.get("organization_id"),selected.get("family")));var items=result.putArray("items");
        for(String modelId:data.db.queryForList("SELECT m.id"+from+" ORDER BY m.created_at DESC,m.id LIMIT ? OFFSET ?",String.class,selected.get("organization_id"),selected.get("family"),size,(page-1L)*size))items.add(getModel(user,modelId));
        return result;
    }
    ObjectNode modelJson(Map<String,Object> row){
        var result=data.json.createObjectNode().put("modelId",row.get("id").toString()).put("datasetId",row.get("dataset_id").toString()).put("runId",row.get("run_id").toString()).put("name",row.get("name").toString()).put("family",row.get("family").toString()).put("organizationId",row.get("organization_id").toString()).put("archived",Boolean.TRUE.equals(row.get("archived"))).put("createdAt",row.get("created_at").toString());
        if(row.get("dataset_name")!=null)result.put("datasetName",row.get("dataset_name").toString());
        if(row.get("input_version_id")!=null)result.put("inputVersionId",row.get("input_version_id").toString());
        result.put("logicalModelId",Objects.toString(row.get("logical_model_id"),row.get("id").toString())).put("versionNumber",row.get("version_number")==null?1:((Number)row.get("version_number")).intValue());
        if(row.get("parent_model_id")!=null)result.put("parentModelId",row.get("parent_model_id").toString());
        result.set("manifest",JsonSupport.parse(data.json,row.get("manifest_json").toString()));
        try{var folder=directory(row.get("run_id").toString()).resolve("output");long bytes=0;
            if("bert".equals(row.get("family"))&&Files.isDirectory(folder.resolve("bert"))){try(var paths=Files.walk(folder.resolve("bert"))){bytes=paths.filter(Files::isRegularFile).filter(p->p.toString().endsWith(".safetensors")||p.toString().endsWith("pytorch_model.bin")).mapToLong(p->{try{return Files.size(p);}catch(IOException e){return 0;}}).sum();}}
            else {var weights=folder.resolve(Set.of("lr","svm","rf").contains(row.get("family"))?"model.joblib":"best.pt");if(Files.isRegularFile(weights))bytes=Files.size(weights);}
            if(bytes>0)result.put("modelBytes",bytes);
        }catch(IOException ignored){}return result;
    }
    public JsonNode updateModel(CurrentUser user,String id,String name,Boolean archived){
        model(user,id);if(name==null && archived==null)throw invalid("请填写修改内容");String label=name==null?null:DatasetService.name(name);
        data.transactions.executeWithoutResult(tx->{data.db.queryForObject("SELECT id FROM ml_model WHERE id=? FOR UPDATE",String.class,id);if(Boolean.TRUE.equals(archived)&&data.db.queryForObject("SELECT COUNT(*) FROM model_release_pointer p JOIN model_release r ON r.id=p.release_id WHERE r.model_id=? OR JSON_SEARCH(r.manifest_json,'one',?,NULL,'$.members[*].modelId') IS NOT NULL",Integer.class,id,id)>0)throw new ApiException(409,"MODEL_IN_USE","该模型正在发布使用，请先回退或撤销发布");if(label!=null)data.db.update("UPDATE ml_model SET name=? WHERE id=?",label,id);if(archived!=null)data.db.update("UPDATE ml_model SET archived=? WHERE id=?",archived,id);});return modelJson(model(user,id));
    }
    public Path artifact(CurrentUser user,String run,String name){
        var task=data.runRow(user,run);
        if(!ACTIONS.contains(task.get("action")) || !"COMPLETED".equals(task.get("status")) || !Set.of("manifest.json","history.json","train.jsonl","validation.jsonl","test.jsonl","calibration.jsonl","segments.jsonl","predictions.jsonl","pairs.jsonl","quarantine.jsonl").contains(name))throw DatasetService.missing();
        var path=directory(run).resolve("output").resolve(name);if(!Files.isRegularFile(path))throw DatasetService.missing();return path;
    }
    public JsonNode samples(CurrentUser user,String id,String kind,int page,int size)throws Exception{
        if(page<1 || size<1 || size>100 || !Set.of("pairs","quarantine").contains(kind))throw invalid("样本分页参数无效");
        Path file=artifact(user,id,kind+".jsonl");var result=data.json.createObjectNode().put("page",page).put("pageSize",size);var items=result.putArray("items");
        long total=0;try(var reader=Files.newBufferedReader(file)){String line;long begin=(long)(page-1)*size;while((line=reader.readLine())!=null){if(total>=begin && items.size()<size)items.add(data.json.readTree(line));total++;}}
        result.put("total",total);return result;
    }
    public JsonNode predictions(CurrentUser user,String id,int page,int size,String q,Integer predicted,String outcome)throws Exception{
        data.role(user);predictionFilters(page,size,q,predicted,outcome);
        var task=data.runRow(user,id);
        if(!Set.of("PREDICT","EVALUATE").contains(task.get("action"))||!"COMPLETED".equals(task.get("status")))throw new ApiException(409,"RESULT_NOT_READY","请选择已完成的评价或预测任务");
        Path output=directory(id).resolve("output"),manifestFile=output.resolve("manifest.json"),file=output.resolve("predictions.jsonl");
        if(!Files.isRegularFile(manifestFile)||!Files.isRegularFile(file)||!manifestFile.toRealPath().startsWith(output.toRealPath())||!file.toRealPath().startsWith(output.toRealPath()))throw DatasetService.missing();
        var manifest=data.json.readTree(Files.readString(manifestFile));
        if(!TrainingAnalyticsService.sameArtifactIdentity(manifest,JsonSupport.parse(data.json,task.get("result_json").toString())))throw new ApiException(409,"ARTIFACT_CHANGED","结果工件发生变化，请重新执行任务");
        return predictionPage(data.json,file,manifest,page,size,q,predicted,outcome);
    }
    public JsonNode predictFile(CurrentUser user,String modelId,MultipartFile file)throws Exception{
        var selected=model(user,modelId);
        if(Boolean.TRUE.equals(selected.get("archived")))throw invalid("请先恢复模型");
        var trained=data.runRow(user,selected.get("run_id").toString());
        String id=DatasetService.uuid();Path folder=directory(id);Files.createDirectories(folder);
        var descriptor=storePredictionInput(data.json,file,folder);
        var options=data.json.createObjectNode().put("name",selected.get("name").toString()+" · 文件预测").put("modelId",modelId).put("inputKind","UPLOADED_FILE");
        options.set("predictionInput",descriptor);
        options.put("inputName",descriptor.path("name").asText()).put("inputSha256",descriptor.path("sha256").asText());
        try{
            data.transactions.executeWithoutResult(tx->{
                if(Boolean.TRUE.equals(data.db.queryForObject("SELECT archived FROM ml_model WHERE id=? FOR UPDATE",Boolean.class,modelId)))throw new ApiException(409,"MODEL_ARCHIVED","请先恢复模型");
                if(Boolean.TRUE.equals(data.db.queryForObject("SELECT archived FROM ml_dataset WHERE id=? FOR UPDATE",Boolean.class,trained.get("dataset_id"))))throw new ApiException(409,"DATASET_ARCHIVED","请先恢复模型所属数据集");
                data.insertRun(id,trained.get("dataset_id").toString(),trained.get("input_version_id").toString(),null,"PREDICT","{}",options.toString(),user.userId());
            });
        }catch(Exception error){Files.deleteIfExists(folder.resolve("prediction-source."+descriptor.path("format").asText()));throw error;}
        return data.json.createObjectNode().put("runId",id);
    }
    static ObjectNode storePredictionInput(com.fasterxml.jackson.databind.ObjectMapper json,MultipartFile file,Path folder)throws Exception{
        if(file==null||file.isEmpty())throw new ApiException(400,"VALIDATION_ERROR","请选择预测文件");
        if(file.getSize()>DatasetService.UPLOAD_LIMIT)throw new ApiException(413,"UPLOAD_TOO_LARGE","预测文件不能超过50MiB");
        String name=Objects.toString(file.getOriginalFilename(),"").replace('\\','/');name=name.substring(name.lastIndexOf('/')+1);
        if(name.isBlank()||name.length()>200||name.chars().anyMatch(c->Character.isISOControl(c)))throw new ApiException(400,"VALIDATION_ERROR","预测文件名无效");
        String lower=name.toLowerCase(Locale.ROOT),format=lower.endsWith(".csv")?"csv":lower.endsWith(".jsonl")?"jsonl":null;
        if(format==null)throw new ApiException(415,"UNSUPPORTED_DATASET","预测文件仅支持CSV或JSONL");
        Path target=folder.resolve("prediction-source."+format);var digest=MessageDigest.getInstance("SHA-256");long bytes=0;
        Files.createFile(target);
        try(var input=file.getInputStream();var output=Files.newOutputStream(target,StandardOpenOption.WRITE)){
            byte[] buffer=new byte[65536];int size;while((size=input.read(buffer))!=-1){bytes+=size;if(bytes>DatasetService.UPLOAD_LIMIT)throw new ApiException(413,"UPLOAD_TOO_LARGE","预测文件不能超过50MiB");digest.update(buffer,0,size);output.write(buffer,0,size);}
        }catch(Exception error){Files.deleteIfExists(target);throw error;}
        return json.createObjectNode().put("format",format).put("name",name).put("sha256",HexFormat.of().formatHex(digest.digest()));
    }
    private static ApiException resultChanged(){return new ApiException(409,"ARTIFACT_CHANGED","预测结果不完整或校验失败，请重新执行任务");}
    private static void predictionFilters(int page,int size,String q,Integer predicted,String outcome){
        if(page<1||size<1||size>100||q==null||q.length()>120||predicted!=null&&predicted!=0&&predicted!=1||!Set.of("all","FP","FN","TP","TN").contains(Objects.toString(outcome,"")))throw new ApiException(400,"VALIDATION_ERROR","预测结果筛选或分页参数无效");
    }
    /** One bounded-memory pass both hashes the immutable file and selects a result page. */
    static ObjectNode predictionPage(com.fasterxml.jackson.databind.ObjectMapper json,Path file,JsonNode manifest,int page,int size,String q,Integer predicted,String outcome)throws Exception{
        predictionFilters(page,size,q,predicted,outcome);
        String expected=manifest.path("artifacts").path("predictions.jsonl").asText();
        boolean evaluation="EVALUATION".equals(manifest.path("taskType").asText());
        if(!"COMPLETED".equals(manifest.path("status").asText())||!Set.of("EVALUATION","PREDICTION").contains(manifest.path("taskType").asText())||!expected.matches("[0-9a-f]{64}"))throw resultChanged();
        long expectedRows=evaluation?manifest.path("metrics").path("rows").asLong(-1):manifest.path("count").asLong(-1);
        if(expectedRows<1||expectedRows>100000)throw resultChanged();
        var result=json.createObjectNode().put("page",page).put("pageSize",size);var items=result.putArray("items");
        var digest=MessageDigest.getInstance("SHA-256");long count=0,total=0,begin=(page-1L)*size;String type=null,query=q.toLowerCase(Locale.ROOT);
        try(var stream=new DigestInputStream(Files.newInputStream(file),digest);var reader=new BufferedReader(new InputStreamReader(stream,StandardCharsets.UTF_8))){
            String line;while((line=predictionLine(reader))!=null){
                if(++count>100000||line.isBlank())throw resultChanged();var row=json.readTree(line);
                if(row==null||!row.isObject()||!row.path("sentence1").isTextual()||!row.path("sentence2").isTextual()||!row.path("predicted").isIntegralNumber()||!Set.of(0,1).contains(row.path("predicted").asInt())||!row.path("score").isNumber()||!Double.isFinite(row.path("score").asDouble())||evaluation&&!row.has("label")||row.has("label")&&(!row.path("label").isIntegralNumber()||!Set.of(0,1).contains(row.path("label").asInt())))throw resultChanged();
                String rowType=row.path("scoreType").asText();if(!Set.of("margin","probability").contains(rowType)||type!=null&&!type.equals(rowType))throw resultChanged();type=rowType;
                String actualOutcome=row.has("label")?(row.path("label").asInt()==1?(row.path("predicted").asInt()==1?"TP":"FN"):(row.path("predicted").asInt()==1?"FP":"TN")):null;
                boolean matches=(predicted==null||row.path("predicted").asInt()==predicted)&&(outcome.equals("all")||outcome.equals(actualOutcome))&&(query.isBlank()||row.path("sentence1").asText().toLowerCase(Locale.ROOT).contains(query)||row.path("sentence2").asText().toLowerCase(Locale.ROOT).contains(query)||row.path("id").asText().toLowerCase(Locale.ROOT).contains(query));
                if(matches){if(total>=begin&&items.size()<size){var item=json.createObjectNode();for(String key:List.of("id","sentence1","sentence2","score","predicted","label","scoreType"))if(row.has(key))item.set(key,row.get(key));if(actualOutcome!=null)item.put("outcome",actualOutcome);items.add(item);}total++;}
            }
        }catch(com.fasterxml.jackson.core.JacksonException error){throw resultChanged();}
        if(count!=expectedRows||!HexFormat.of().formatHex(digest.digest()).equals(expected))throw resultChanged();
        result.put("count",count).put("total",total).put("scoreType",type);return result;
    }
    static String predictionLine(Reader reader)throws IOException{
        // Uploaded batches are capped at100k rows; one oversized/corrupt row must not grow memory unboundedly.
        var line=new StringBuilder();int value;
        while((value=reader.read())!=-1){if(value=='\n')return line.toString();if(line.length()>=8*1024*1024)throw resultChanged();line.append((char)value);}
        return line.isEmpty()?null:line.toString();
    }
}
