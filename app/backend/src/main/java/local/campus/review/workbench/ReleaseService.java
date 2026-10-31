package local.campus.review.workbench;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.detection.DetectorClient;
import local.campus.review.reference.LibraryGenerationService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;
@Service
public class ReleaseService {
    final DatasetService data;final TrainingService training;final LibraryGenerationService libraries;final DetectorClient detector;
    public ReleaseService(DatasetService data,TrainingService training,LibraryGenerationService libraries,DetectorClient detector){this.data=data;this.training=training;this.libraries=libraries;this.detector=detector;}
    public record Create(String organizationId,String scene,String name,String modelId,String evaluationId,String preset,String profileId){}
    public record BundleCreate(String organizationId,String bundleId,String name){}
    public JsonNode createBundle(CurrentUser actor,BundleCreate input){
        AccessPolicy.requireAdmin(actor);DatasetService.identity(input.bundleId());String name=DatasetService.name(input.name());
        String org=input.organizationId();if(org==null||org.equals("0"))org=null;else data.organization(actor,org);
        var rows=data.db.queryForList("SELECT * FROM ml_pipeline WHERE id=?",input.bundleId());if(rows.isEmpty())throw DatasetService.missing();var group=rows.getFirst();
        if(((Number)group.get("bundle_version")).intValue()!=1||!"COMPLETED".equals(group.get("status"))||Boolean.TRUE.equals(group.get("archived")))throw new ApiException(400,"BUNDLE_INCOMPLETE","请等待六模型训练及独立评价全部完成");
        var dataset=data.dataset(actor,group.get("dataset_id").toString());if(org!=null&&!org.equals(dataset.get("organization_id").toString()))throw new ApiException(400,"VALIDATION_ERROR","模型组与目标部门不匹配");
        var state=JsonSupport.parse(data.json,group.get("state_json").toString());var snapshot=data.json.createObjectNode().put("bundleId",input.bundleId());var members=snapshot.putArray("members");var families=new HashSet<String>();
        for(var member:state.path("models")){
            String family=member.path("family").asText(),modelId=member.path("modelId").asText(),evaluationId=member.path("evaluationRunId").asText();
            var model=training.model(actor,modelId);var evaluation=data.runRow(actor,evaluationId);var options=JsonSupport.parse(data.json,evaluation.get("options_json").toString());
            var run=data.runRow(actor,model.get("run_id").toString());var trainingOptions=JsonSupport.parse(data.json,run.get("options_json").toString());
            if(!TrainingService.FAMILIES.contains(family)||!families.add(family)||!family.equals(model.get("family"))||Boolean.TRUE.equals(model.get("archived"))||!"COMPLETED".equals(run.get("status"))||!"EVALUATE".equals(evaluation.get("action"))||!"COMPLETED".equals(evaluation.get("status"))||!modelId.equals(options.path("modelId").asText())||!state.path("preparationId").asText().equals(options.path("preparationId").asText())||!state.path("preparationId").asText().equals(trainingOptions.path("preparationId").asText()))throw new ApiException(409,"BUNDLE_CHANGED","模型组成员、划分或评价不完整");
            var binding=members.addObject().put("family",family).put("modelId",modelId).put("evaluationId",evaluationId).put("model",training.directory(model.get("run_id").toString()).resolve("output").toString()).put("evaluation",training.directory(evaluationId).resolve("output/manifest.json").toString()).put("preparation",training.directory(state.path("preparationId").asText()).resolve("output").toString()).put("modelManifestSha256",training.modelManifestHash(model.get("run_id").toString()));
            try{binding.put("evaluationSha256",sha(training.directory(evaluationId).resolve("output/manifest.json"))).put("preparationSha256",sha(training.directory(state.path("preparationId").asText()).resolve("output/manifest.json")));}catch(Exception e){throw new ApiException(409,"BUNDLE_CHANGED","模型组评价或样本工件不可读取");}
        }
        if(families.size()!=6)throw new ApiException(400,"BUNDLE_INCOMPLETE","发布须包含全部六种算法");String id=DatasetService.uuid();
        data.db.update("INSERT INTO model_release(id,organization_id,scene,name,preset,bundle_id,bundle_snapshot_json,status,created_by,created_at) VALUES(?,?,'TEXT_REUSE',?,'SIX_MODEL',?,?,'QUEUED',?,UTC_TIMESTAMP(3))",id,org,name,input.bundleId(),snapshot.toString(),actor.userId());return data.json.createObjectNode().put("id",id);
    }
    public JsonNode create(CurrentUser actor,Create input){
        AccessPolicy.requireAdmin(actor);String org=input.organizationId();if(org!=null&&!org.equals("0"))data.organization(actor,org);else org=null;
        if("PAIR_PREDICTION".equals(input.scene())||"WEB_BERT".equals(input.preset()))throw new ApiException(400,"BUNDLE_REQUIRED","模型发布请使用完整六模型组");
        if(!Set.of("TEXT_REUSE","PAIR_PREDICTION").contains(Objects.toString(input.scene(),"")))throw new ApiException(400,"VALIDATION_ERROR","请选择发布场景");String name=DatasetService.name(input.name());
        boolean web="TEXT_REUSE".equals(input.scene())&&"WEB_BERT".equals(input.preset());
        if(input.scene().equals("TEXT_REUSE")){if(!Set.of("CURRENT","LEGACY","CAMPUS_V3","WEB_BERT").contains(Objects.toString(input.preset(),"")))throw new ApiException(400,"VALIDATION_ERROR","请选择兼容的审核配置");if("CAMPUS_V3".equals(input.preset()))DatasetService.identity(input.profileId());}
        if(!input.scene().equals("TEXT_REUSE")||web){var model=training.model(actor,input.modelId());if(Boolean.TRUE.equals(model.get("archived")))throw new ApiException(409,"MODEL_ARCHIVED","请先恢复模型");if(org!=null&&!org.equals(model.get("organization_id").toString()))throw new ApiException(400,"VALIDATION_ERROR","模型与目标部门不匹配");if(web&&(!"bert".equals(model.get("family"))||JsonSupport.parse(data.json,model.get("manifest_json").toString()).path("parameters").path("max_length").asInt()<128))throw new ApiException(400,"VALIDATION_ERROR","请选择兼容128词元的BERT模型版本");var evaluation=data.runRow(actor,input.evaluationId());if(!"EVALUATE".equals(evaluation.get("action"))||!"COMPLETED".equals(evaluation.get("status"))||!input.modelId().equals(JsonSupport.parse(data.json,evaluation.get("options_json").toString()).path("modelId").asText()))throw new ApiException(400,"VALIDATION_ERROR","请选择该模型已完成的独立评价");}
        String id=UUID.randomUUID().toString();boolean usesModel=web||!input.scene().equals("TEXT_REUSE");data.db.update("INSERT INTO model_release(id,organization_id,scene,name,model_id,evaluation_run_id,preset,profile_id,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,'QUEUED',?,UTC_TIMESTAMP(3))",id,org,input.scene(),name,usesModel?input.modelId():null,usesModel?input.evaluationId():null,input.scene().equals("TEXT_REUSE")?input.preset():null,input.scene().equals("TEXT_REUSE")&&"CAMPUS_V3".equals(input.preset())?input.profileId():null,actor.userId());return data.json.createObjectNode().put("id",id);
    }
    public JsonNode textProfiles(CurrentUser actor)throws Exception{
        data.role(actor);
        return ProjectPython.delivery(data.settings,data.json,data.settings.runtime().resolve("delivery/profile-queries").resolve(UUID.randomUUID().toString()),data.json.createObjectNode().put("action","PROFILE_CANDIDATES"));
    }
    public JsonNode list(CurrentUser actor,int page){return list(actor,page,20);}
    public JsonNode get(CurrentUser actor,String id){
        data.role(actor);DatasetService.identity(id);var rows=data.db.queryForList("SELECT r.*,o.name AS department FROM model_release r LEFT JOIN organization o ON o.id=r.organization_id WHERE r.id=?",id);if(rows.isEmpty())throw DatasetService.missing();var row=rows.getFirst();
        var result=data.json.createObjectNode().put("id",id).put("name",row.get("name").toString()).put("scene",row.get("scene").toString()).put("organizationId",Objects.toString(row.get("organization_id"),"0")).put("department",Objects.toString(row.get("department"),"校级默认")).put("status",row.get("status").toString()).put("error",Objects.toString(row.get("error_message"),"")).put("active",data.db.queryForObject("SELECT COUNT(*) FROM model_release_pointer WHERE release_id=?",Integer.class,id)>0);
        if(row.get("manifest_json")!=null)result.set("manifest",JsonSupport.parse(data.json,row.get("manifest_json").toString()));return result;
    }
    public JsonNode list(CurrentUser actor,int page,int size){data.role(actor);if(page<1 || size<1 || size>100)throw new ApiException(400,"VALIDATION_ERROR","分页无效");var result=data.json.createObjectNode().put("page",page).put("pageSize",size).put("total",data.db.queryForObject("SELECT COUNT(*) FROM model_release",Long.class));var items=result.putArray("items");for(var row:data.db.queryForList("SELECT r.*,o.name AS department FROM model_release r LEFT JOIN organization o ON o.id=r.organization_id ORDER BY r.created_at DESC,r.id DESC LIMIT ? OFFSET ?",size,(page-1L)*size)){var item=data.json.createObjectNode().put("id",row.get("id").toString()).put("name",row.get("name").toString()).put("scene",row.get("scene").toString()).put("organizationId",Objects.toString(row.get("organization_id"),"0")).put("department",Objects.toString(row.get("department"),"校级默认")).put("status",row.get("status").toString()).put("error",Objects.toString(row.get("error_message"),""));if(row.get("manifest_json")!=null)item.set("manifest",JsonSupport.parse(data.json,row.get("manifest_json").toString()));items.add(item);}result.set("pointers",data.json.valueToTree(data.db.queryForList("SELECT scope_key AS scopeKey,release_id AS releaseId FROM model_release_pointer")));result.set("history",data.json.valueToTree(data.db.queryForList("SELECT scope_key AS scopeKey,previous_id AS previousId,release_id AS releaseId,DATE_FORMAT(created_at,'%Y-%m-%dT%H:%i:%sZ') AS createdAt FROM model_release_event ORDER BY id DESC LIMIT 20")));return result;}
    public JsonNode history(CurrentUser actor,int page,int size){
        data.role(actor);if(page<1 || size<1 || size>100)throw new ApiException(400,"VALIDATION_ERROR","分页无效");
        var result=data.json.createObjectNode().put("page",page).put("pageSize",size).put("total",data.db.queryForObject("SELECT COUNT(*) FROM model_release_event",Long.class));
        result.set("items",data.json.valueToTree(data.db.queryForList("SELECT scope_key AS scopeKey,previous_id AS previousId,release_id AS releaseId,DATE_FORMAT(created_at,'%Y-%m-%dT%H:%i:%sZ') AS createdAt FROM model_release_event ORDER BY id DESC LIMIT ? OFFSET ?",size,(page-1L)*size)));return result;
    }
    public JsonNode evaluations(CurrentUser actor,String model){training.model(actor,model);return data.json.valueToTree(data.db.queryForList("SELECT id AS runId,JSON_UNQUOTE(JSON_EXTRACT(options_json,'$.name')) AS name FROM ml_run WHERE action='EVALUATE' AND status='COMPLETED' AND JSON_UNQUOTE(JSON_EXTRACT(options_json,'$.modelId'))=? ORDER BY created_at DESC LIMIT 100",model));}
    @Transactional public JsonNode activate(CurrentUser actor,String id,String expected){
        AccessPolicy.requireAdmin(actor);DatasetService.identity(id);var row=data.db.queryForMap("SELECT * FROM model_release WHERE id=?",id);if(!"READY".equals(row.get("status")))throw new ApiException(409,"RELEASE_NOT_READY","请等待版本核验完成");
        String org=Objects.toString(row.get("organization_id"),"0"),scene=row.get("scene").toString(),scope=org+":"+scene;if(!org.equals("0"))data.organization(actor,org);
        var manifest=JsonSupport.parse(data.json,row.get("manifest_json").toString());try{var files=manifest.path("verifiedFiles").fields();while(files.hasNext()){var entry=files.next();var file=data.settings.root().resolve(entry.getKey()).normalize();if(!file.startsWith(data.settings.root())||!sha(file).equals(entry.getValue().asText()))throw new IllegalStateException();}}catch(Exception e){throw new ApiException(409,"ARTIFACT_CHANGED","已核验工件发生变化，请重新登记版本");}
        if(row.get("bundle_id")!=null){
            if(!row.get("bundle_id").equals(manifest.path("bundleId").asText())||manifest.path("members").size()!=6)throw new ApiException(409,"BUNDLE_CHANGED","模型组核验身份不一致");
            var memberIds=new TreeSet<String>();for(var member:manifest.path("members"))memberIds.add(member.path("modelId").asText());if(memberIds.size()!=6)throw new ApiException(409,"BUNDLE_CHANGED","模型组成员身份重复");
            for(String memberId:memberIds)if(Boolean.TRUE.equals(data.db.queryForObject("SELECT archived FROM ml_model WHERE id=? FOR UPDATE",Boolean.class,memberId)))throw new ApiException(409,"MODEL_ARCHIVED","模型组成员已归档，请恢复后发布");
        }
        if(scene.equals("TEXT_REUSE")){
            detector.ensureTextAdapter(manifest);
            // Share the reference switch lock so validation and pointer activation see one generation.
            data.db.update("INSERT IGNORE INTO runtime_state(name,library_generation_id,updated_at) VALUES('CURRENT_LIBRARY',NULL,UTC_TIMESTAMP(3))");
            var libraryPointer=data.db.queryForMap("SELECT library_generation_id FROM runtime_state WHERE name='CURRENT_LIBRARY' FOR UPDATE");
            String generation=Objects.toString(libraryPointer.get("library_generation_id"),"");
            if(generation.isEmpty())throw new ApiException(409,"INDEX_NOT_READY","请先准备参考库索引");
            if(isV3(manifest)){
                String hash=data.db.queryForObject("SELECT manifest_sha256 FROM library_generation WHERE id=? FOR UPDATE",String.class,generation);
                requireProfileLibrary(manifest,generation,hash);requireProfileLoaded(manifest,detector.health(false));
            }
            if(!manifest.path("textConfig").path("featureSpaceId").equals(libraries.lockedManifest(generation).path("producerConfigs").path("textConfig").path("featureSpaceId")))throw new ApiException(409,"INDEX_INCOMPATIBLE","当前参考库特征空间不兼容，请先准备匹配索引");
        }
        data.db.update("INSERT IGNORE INTO model_release_pointer(scope_key,release_id,updated_at) VALUES(?,NULL,UTC_TIMESTAMP(3))",scope);var pointer=data.db.queryForMap("SELECT release_id FROM model_release_pointer WHERE scope_key=? FOR UPDATE",scope);String old=Objects.toString(pointer.get("release_id"),"");if(!old.equals(Objects.toString(expected,"")))throw new ApiException(409,"RELEASE_CONFLICT","活动版本已变化，请刷新后重试");
        if(row.get("model_id")!=null){var model=data.db.queryForMap("SELECT archived,run_id FROM ml_model WHERE id=? FOR UPDATE",row.get("model_id"));if(Boolean.TRUE.equals(model.get("archived")))throw new ApiException(409,"MODEL_ARCHIVED","发布模型已归档");try{String actual=sha(training.directory(model.get("run_id").toString()).resolve("output/manifest.json"));if(!actual.equals(manifest.path("modelManifestSha256").asText()))throw new IllegalStateException();}catch(Exception e){throw new ApiException(409,"MODEL_CHANGED","模型工件已变化，请重新登记核验");}}
        data.db.update("UPDATE model_release_pointer SET release_id=?,updated_at=UTC_TIMESTAMP(3) WHERE scope_key=?",id,scope);data.db.update("INSERT INTO model_release_event(scope_key,previous_id,release_id,actor_id,created_at) VALUES(?,?,?,?,UTC_TIMESTAMP(3))",scope,old.isEmpty()?null:old,id,actor.userId());return data.json.createObjectNode().put("activeId",id);
    }
    private static byte[] hashStream(java.io.InputStream stream)throws Exception{var hash=java.security.MessageDigest.getInstance("SHA-256");byte[] buffer=new byte[65536];int n;while((n=stream.read(buffer))!=-1)hash.update(buffer,0,n);return hash.digest();}
    static String sha(java.nio.file.Path file)throws Exception{try(var stream=java.nio.file.Files.newInputStream(file)){return HexFormat.of().formatHex(hashStream(stream));}}
    @Transactional public JsonNode reset(CurrentUser actor,String org,String scene,String expected){AccessPolicy.requireAdmin(actor);if(!Set.of("TEXT_REUSE","PAIR_PREDICTION").contains(scene))throw new ApiException(400,"VALIDATION_ERROR","场景无效");if(!org.equals("0"))data.organization(actor,org);String key=org+":"+scene;data.db.update("INSERT IGNORE INTO model_release_pointer(scope_key,updated_at) VALUES(?,UTC_TIMESTAMP(3))",key);var row=data.db.queryForMap("SELECT release_id FROM model_release_pointer WHERE scope_key=? FOR UPDATE",key);String old=Objects.toString(row.get("release_id"),"");if(!old.equals(Objects.toString(expected,"")))throw new ApiException(409,"RELEASE_CONFLICT","活动版本已变化，请刷新");data.db.update("UPDATE model_release_pointer SET release_id=NULL,updated_at=UTC_TIMESTAMP(3) WHERE scope_key=?",key);data.db.update("INSERT INTO model_release_event(scope_key,previous_id,release_id,actor_id,created_at) VALUES(?,?,NULL,?,UTC_TIMESTAMP(3))",key,old.isEmpty()?null:old,actor.userId());return data.json.createObjectNode().put("reset",true);}
    public ObjectNode textSelection(String org,JsonNode fallback,String generation,String libraryHash){
        var rows=data.db.queryForList("SELECT r.id,r.manifest_json FROM model_release_pointer p JOIN model_release r ON r.id=p.release_id WHERE p.scope_key IN (?,?) ORDER BY (p.scope_key=?) DESC LIMIT 1",org+":TEXT_REUSE","0:TEXT_REUSE",org+":TEXT_REUSE");var result=data.json.createObjectNode();if(rows.isEmpty()){result.set("textConfig",fallback);return result;}
        var manifest=JsonSupport.parse(data.json,rows.getFirst().get("manifest_json").toString());if(isV3(manifest))requireProfileLibrary(manifest,generation,libraryHash);
        detector.ensureTextAdapter(manifest);result.put("releaseId",rows.getFirst().get("id").toString());result.set("textConfig",manifest.path("textConfig"));if(manifest.has("textAdapter"))result.set("textAdapter",manifest.get("textAdapter"));return result;
    }
    private static boolean isV3(JsonNode manifest){return manifest.hasNonNull("profileId")||"text-v3".equals(manifest.path("textConfig").path("schemaVersion").asText());}
    static void requireProfileLibrary(JsonNode manifest,String generation,String hash){
        if(generation==null||generation.isBlank()||hash==null||hash.isBlank()||!generation.equals(manifest.path("libraryGenerationId").asText())||!hash.equals(manifest.path("libraryManifestSha256").asText()))throw new ApiException(409,"REFERENCE_PROFILE_STALE","参考库已变化，请准备并发布匹配的校园模型版本");
    }
    static void requireProfileLoaded(JsonNode manifest,JsonNode health){
        String profile=manifest.path("profileId").asText(),config=manifest.path("textConfig").path("configId").asText();
        if(health.path("ready").asBoolean()&&!profile.isBlank()&&!config.isBlank())for(var available:health.path("availableTextConfigs"))if(profile.equals(available.path("profileId").asText())&&config.equals(available.path("configId").asText()))return;
        throw new ApiException(409,"PROFILE_NOT_LOADED","检测服务尚未加载该校园模型，请加载对应版本后再发布");
    }
    public JsonNode predict(CurrentUser actor,String org,JsonNode rows)throws Exception{
        data.organization(actor,org);if(rows==null||!rows.isArray()||rows.isEmpty()||rows.size()>100)throw new ApiException(400,"VALIDATION_ERROR","每次可提交1—100组句对");for(var row:rows)for(String key:List.of("sentence1","sentence2"))if(!row.path(key).isTextual()||row.path(key).asText().isBlank()||row.path(key).asText().length()>10000)throw new ApiException(400,"VALIDATION_ERROR","请填写有效文本，每段最多10000字符");
        var releases=data.db.queryForList("SELECT r.* FROM model_release_pointer p JOIN model_release r ON r.id=p.release_id WHERE p.scope_key IN (?,?,?,?) AND (r.scene='PAIR_PREDICTION' OR r.bundle_id IS NOT NULL) ORDER BY (r.bundle_id IS NOT NULL) DESC,(p.scope_key LIKE ?) DESC LIMIT 1",org+":TEXT_REUSE","0:TEXT_REUSE",org+":PAIR_PREDICTION","0:PAIR_PREDICTION",org+":%");if(releases.isEmpty())throw new ApiException(409,"NO_ACTIVE_MODEL","该部门尚无已发布的句对模型");var release=releases.getFirst();if(release.get("bundle_id")!=null){String predictionId=DatasetService.uuid();var published=JsonSupport.parse(data.json,release.get("manifest_json").toString());var request=data.json.createObjectNode().put("action","BUNDLE_PREDICT");request.set("textAdapter",published.path("textAdapter"));request.set("rows",rows);var prediction=(ObjectNode)ProjectPython.delivery(data.settings,data.json,data.settings.runtime().resolve("delivery/predictions").resolve(predictionId),request);prediction.put("predictionId",predictionId).put("releaseId",release.get("id").toString());data.db.update("INSERT INTO model_release_prediction(id,release_id,input_sha256,result_json,created_by,created_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3))",predictionId,release.get("id"),JsonSupport.hash(data.json,rows),prediction.toString(),actor.userId());return prediction;}var model=training.model(actor,release.get("model_id").toString());if(Boolean.TRUE.equals(model.get("archived")))throw new ApiException(409,"MODEL_ARCHIVED","发布模型已归档，请选择可用版本");String id=UUID.randomUUID().toString();var manifest=JsonSupport.parse(data.json,release.get("manifest_json").toString());var config=data.json.createObjectNode().put("action","PREDICT").put("model",training.directory(model.get("run_id").toString()).resolve("output").toString()).put("modelManifestSha256",manifest.path("modelManifestSha256").asText());config.set("rows",rows);var result=(ObjectNode)ProjectPython.delivery(data.settings,data.json,data.settings.runtime().resolve("delivery/predictions").resolve(id),config);result.put("predictionId",id).put("releaseId",release.get("id").toString());data.db.update("INSERT INTO model_release_prediction(id,release_id,input_sha256,result_json,created_by,created_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3))",id,release.get("id"),JsonSupport.hash(data.json,rows),result.toString(),actor.userId());return result;
    }
    public void verify(Map<String,Object> row)throws Exception{
        String id=row.get("id").toString();var folder=data.settings.runtime().resolve("delivery/releases").resolve(id);var config=data.json.createObjectNode();
        if("SIX_MODEL".equals(row.get("preset"))){
            config.setAll((ObjectNode)JsonSupport.parse(data.json,row.get("bundle_snapshot_json").toString()));config.put("action","SIX_MODEL_BUNDLE").put("output",folder.toString());
            var result=ProjectPython.delivery(data.settings,data.json,folder,config);detector.ensureTextAdapter(result);
            data.db.update("UPDATE model_release SET status='READY',manifest_json=?,error_message=NULL WHERE id=?",result.toString(),id);return;
        }
        boolean web="WEB_BERT".equals(row.get("preset"));
        if(web){var health=detector.health(false);if(!health.path("ready").asBoolean())throw new DetectorClient.DetectorFailure("MODELS_NOT_READY");if(health.path("busy").asBoolean())throw new DetectorClient.DetectorFailure("PROCESS_BUSY");}
        if("CAMPUS_V3".equals(row.get("preset"))){String profile=Objects.toString(row.get("profile_id"),"");DatasetService.identity(profile);config.put("action","V3_CONFIG").put("profileId",profile);}
        else if(row.get("model_id")==null)config.put("action","CONFIG").put("preset",row.get("preset").toString());
        else{
            String run=data.db.queryForObject("SELECT run_id FROM ml_model WHERE id=?",String.class,row.get("model_id"));
            config.put("action",web?"WEB_BERT":"MODEL").put("model",training.directory(run).resolve("output").toString()).put("evaluation",training.directory(row.get("evaluation_run_id").toString()).resolve("output/manifest.json").toString());
            var evaluationOptions=JsonSupport.parse(data.json,data.db.queryForObject("SELECT options_json FROM ml_run WHERE id=?",String.class,row.get("evaluation_run_id")));
            config.put("evaluationPreparation",training.directory(evaluationOptions.path("preparationId").asText()).resolve("output").toString());
            if(web){var options=JsonSupport.parse(data.json,data.db.queryForObject("SELECT options_json FROM ml_run WHERE id=?",String.class,run));config.put("modelId",row.get("model_id").toString()).put("evaluationId",row.get("evaluation_run_id").toString()).put("preparation",training.directory(options.path("preparationId").asText()).resolve("output").toString()).put("output",folder.toString());}
        }
        var result=(ObjectNode)ProjectPython.delivery(data.settings,data.json,folder,config);
        if(web){
            detector.ensureTextAdapter(result);
            var development=ProjectPython.delivery(data.settings,data.json,folder.resolve("development"),data.json.createObjectNode().put("action","WEB_BERT_DEVELOPMENT").put("output",folder.toString()).put("configId",result.path("textConfig").path("configId").asText()).put("port",data.settings.port("detector")));
            result.set("development",development.path("development"));((ObjectNode)result.path("verifiedFiles")).setAll((ObjectNode)development.path("verifiedFiles"));
        }
        data.db.update("UPDATE model_release SET status='READY',manifest_json=?,error_message=NULL WHERE id=?",result.toString(),id);
    }
}
