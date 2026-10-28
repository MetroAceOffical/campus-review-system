package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.springframework.stereotype.Service;
import java.io.RandomAccessFile;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;

/** Read-only bridge for explicitly registered offline jobs; never controls a process. */
@Service
public class FormalTrainingService {
    private static final long JSON_BYTES=512*1024,TAIL_BYTES=256*1024;
    private static final int HISTORY_POINTS=500;
    private static final Set<String> LIVE_STATES=Set.of("TRAINING","CORRESPONDENCE_TRAINING","GENERATING_TRAIN_MATERIAL","GENERATING_HELDOUT_QUERIES","WAITING_CAMPUS_TRAINING_COMPLETION","WAITING_GPU_RESOURCE","WAITING_OTHER_GPU_CONSUMER","WAITING_WEB_OR_GPU_RESOURCE","LOADING_IMAGE_EVALUATION","RUNNING_IMAGE_DEVELOPMENT_EVALUATION","WAITING_HOST_MEMORY","WAITING_CPU_EVALUATOR","RUNNING_DOCUMENT_EVALUATION");
    private static final Set<String> METRICS=Set.of("selectedOriginals","elapsedSeconds","estimatedRemainingSeconds","reusedSegments",
        "hostRssBytes","cudaPeakAllocatedBytes","cudaPeakBytes","modelLoadSeconds","processed","total","queries","steps","epochs",
        "plannedSlots","requestedQuerySlots","constructedQueries","pendingSlots","generatedParaphraseQueries","globallySupportedNormalQueries",
        "referenceFields","scheduledSegments","generatedSegments","acceptedSegments","pendingSegments","quarantinedSegments",
        "dinoTop10Retrieved","dinoTop20Retrieved","baselineAccepted","top20Accepted","enhancedAccepted","scopeCorrect",
        "failedQueries","partialQueries","unknownAcceptedSources","finalQueriesEvaluated","realHardNegativeTruthCount",
        "truePositive","falsePositive","falseNegative","invalidSuggestions","assessableFields","correctFields","unresolvedFields",
        "conflictFields","detectedConflicts","falseConflicts","insufficientControls","correctInsufficient","knownContextQueries",
        "relatedTop1","relatedTop3","realRuntimeQueries","realRuntimeCompleted","availableMemoryBytes","requiredMemoryBytes","totalSteps");
    private static final Set<String> FLAGS=Set.of("reloadVerified","qualityAccepted","productActivated","fullQuerySetReady",
        "neuralTrainingStarted","modelEvaluationStarted","neuralTrainingPerformed","modelPredictionsProduced","finalProtocolExecuted");
    private static final Set<String> RECORD=Set.of("step","epoch","loss","validationLoss","baselineValidationLoss","gradientNorm",
        "elapsedSeconds","learningRate","hostRssBytes","cudaPeakAllocatedBytes","cudaPeakBytes","actualQueries","actualPairs",
        "remainingOptimizerSteps","estimatedRemainingSeconds","nextCursor","explicitPassagesPerQuery");
    private final DatasetService data;
    public FormalTrainingService(DatasetService data){this.data=data;}

    public JsonNode progress(CurrentUser user){
        data.role(user);
        return read(data.settings.root(),data.settings.runtime(),data.json,data.settings.root().resolve("app/config/formal-pipeline.json"));
    }

    static ObjectNode read(Path root,Path runtime,ObjectMapper json,Path registry){
        var result=json.createObjectNode().put("observedAt",Instant.now().toString());
        var stages=result.putArray("stages");
        if(!Files.isRegularFile(registry)){result.put("title","正式模型训练").put("configured",false);result.putObject("recipe");return result;}
        try{
            var config=readJson(json,registry);
            if(config.path("schemaVersion").asInt()!=1 || !config.path("stages").isArray() || config.path("stages").size()>20)throw new IllegalArgumentException();
            result.put("title",config.path("title").asText("正式模型训练")).put("configured",true);
            result.set("recipe",recipe(root,runtime,json,config));
            var keys=new HashSet<String>();
            for(var stage:config.path("stages")){
                String key=stage.path("key").asText(),title=stage.path("title").asText();
                if(!key.matches("[a-z][a-z0-9_-]{0,39}")||!keys.add(key)||title.isBlank()||title.length()>100)throw new IllegalArgumentException();
                var item=json.createObjectNode().put("key",key).put("title",title).put("state","NOT_STARTED").put("availability","PENDING");
                item.putObject("metrics");item.putObject("latest");item.putArray("history");item.putArray("splits");
                try{
                    Path folder=inside(root,runtime,stage.path("directory").asText());
                    Path status=child(runtime,folder,stage.path("statusFile").asText("status.json"));
                    if(Files.isRegularFile(status)){
                        var value=readJson(json,status);item.put("state",state(value.path("state").asText("OBSERVED"))).put("availability","AVAILABLE");
                        item.put("updatedAt",Files.getLastModifiedTime(status).toInstant().toString());
                        item.put("stale",LIVE_STATES.contains(item.path("state").asText())&&Files.getLastModifiedTime(status).toInstant().isBefore(Instant.now().minusSeconds(900)));
                        var metrics=(ObjectNode)item.path("metrics");copyScalars(value,metrics,METRICS);copyFlags(value,metrics);
                        var counts=value.path("segmentCounts").isObject()?value.path("segmentCounts"):value.path("counts");
                        if(counts.isObject())for(var entry:Map.of("ACCEPTED","accepted","PENDING","pending","QUARANTINED","quarantined").entrySet()){
                            if(!counts.has(entry.getKey()))metrics.put(entry.getValue(),0);else number(counts,entry.getKey(),metrics,entry.getValue());
                        }
                        number(value,"reusedSegments",metrics,"reused");
                        item.set("latest",record(json,value.path("latest")));
                        var splits=item.withArray("splits");
                        for(String split:List.of("calibration","dev","final")){
                            var source=value.path("splitCounts").path(split);if(!source.isObject())continue;
                            var row=json.createObjectNode().put("split",split);
                            copyScalars(source,row,Set.of("target","constructed","pending","plannedHomePrimaryQueries","constructedHomePrimaryQueries"));
                            if(source.path("homeTargetMetForPlan").isBoolean())row.set("homeTargetMetForPlan",source.get("homeTargetMetForPlan"));splits.add(row);
                        }
                        progress(json,item,value,metrics);
                    }
                    if(stage.hasNonNull("historyFile"))item.set("history",history(json,child(runtime,folder,stage.path("historyFile").asText())));
                }catch(Exception error){item.put("availability","READ_ERROR").put("state","READ_ERROR").put("error","进度文件正在写入或暂不可读取");}
                stages.add(item);
            }
            return result;
        }catch(Exception error){throw new ApiException(503,"FORMAL_PROGRESS_UNAVAILABLE","正式训练进度配置暂不可读取");}
    }

    private static String state(String value){return value.matches("[A-Z][A-Z0-9_]{0,119}")?value:"OBSERVED";}
    private static JsonNode readJson(ObjectMapper json,Path path)throws Exception{
        if(Files.size(path)>JSON_BYTES)throw new IllegalArgumentException();
        var value=json.readTree(Files.readString(path));if(value==null||!value.isObject())throw new IllegalArgumentException();return value;
    }
    private static Path inside(Path root,Path runtime,String relative)throws Exception{
        if(relative.isBlank()||Path.of(relative).isAbsolute())throw new IllegalArgumentException();
        Path path=root.resolve(relative).toAbsolutePath().normalize(),boundary=runtime.toAbsolutePath().normalize();
        if(!path.startsWith(boundary)||path.equals(boundary))throw new IllegalArgumentException();
        if(Files.exists(path)&&!path.toRealPath().startsWith(boundary.toRealPath()))throw new IllegalArgumentException();
        return path;
    }
    private static Path child(Path runtime,Path folder,String relative)throws Exception{
        if(relative.isBlank()||Path.of(relative).isAbsolute())throw new IllegalArgumentException();
        Path path=folder.resolve(relative).normalize();if(!path.startsWith(folder)||path.equals(folder))throw new IllegalArgumentException();
        if(Files.exists(path)&&!path.toRealPath().startsWith(runtime.toRealPath()))throw new IllegalArgumentException();return path;
    }
    private static void number(JsonNode source,String key,ObjectNode target,String name){
        var value=source.path(key);if(value.isNumber()&&Double.isFinite(value.asDouble())&&value.asDouble()>=0)target.set(name,value);
    }
    private static void copyScalars(JsonNode source,ObjectNode target,Set<String> fields){for(String field:fields)number(source,field,target,field);}
    private static void copyFlags(JsonNode source,ObjectNode target){for(String field:FLAGS)if(source.path(field).isBoolean())target.set(field,source.get(field));}
    private static ObjectNode record(ObjectMapper json,JsonNode source){
        var result=json.createObjectNode();copyScalars(source,result,RECORD);
        for(String flag:List.of("parameterSliceChanged","adapterWeightChanged","classifierWeightChanged"))if(source.path(flag).isBoolean())result.set(flag,source.get(flag));
        if(Set.of("epoch_end","start_or_resume").contains(source.path("event").asText()))result.set("event",source.get("event"));
        return result;
    }
    private static JsonNode history(ObjectMapper json,Path path)throws Exception{
        var result=json.createArrayNode();if(!Files.isRegularFile(path))return result;
        // Read only a bounded tail, retaining actual points rather than interpolating a curve.
        try(var file=new RandomAccessFile(path.toFile(),"r")){
            long length=file.length(),start=Math.max(0,length-TAIL_BYTES);file.seek(start);byte[] bytes=new byte[(int)(length-start)];file.readFully(bytes);
            String text=new String(bytes,StandardCharsets.UTF_8);if(start>0){int newline=text.indexOf('\n');text=newline<0?"":text.substring(newline+1);}
            var points=new ArrayDeque<ObjectNode>();
            for(String line:text.split("\n"))try{
                if(line.isBlank())continue;var row=record(json,json.readTree(line));if(row.isEmpty())continue;
                points.addLast(row);if(points.size()>HISTORY_POINTS)points.removeFirst();
            }catch(Exception unfinishedLine){/* An in-progress final line is not an event. */}
            points.forEach(result::add);return result;
        }
    }
    private static void progress(ObjectMapper json,ObjectNode item,JsonNode source,JsonNode metrics){
        Long processed=null,total=null;
        if(metrics.has("accepted")&&metrics.has("pending")&&metrics.has("quarantined")){
            processed=metrics.path("accepted").asLong()+metrics.path("quarantined").asLong();total=processed+metrics.path("pending").asLong();
        }else if(metrics.has("constructedQueries")&&metrics.has("plannedSlots")){
            processed=metrics.path("constructedQueries").asLong();total=metrics.path("plannedSlots").asLong();
        }else if(metrics.has("processed")&&metrics.has("total")){
            processed=metrics.path("processed").asLong();total=metrics.path("total").asLong();
        }else if(source.path("latest").has("step")&&source.path("latest").has("remainingOptimizerSteps")){
            processed=source.path("latest").path("step").asLong();total=processed+source.path("latest").path("remainingOptimizerSteps").asLong();
        }
        if(processed!=null&&total!=null&&total>0&&processed>=0&&processed<=total)item.set("progress",json.createObjectNode().put("processed",processed).put("total",total).put("percent",processed*100.0/total));
    }
    private static ObjectNode recipe(Path root,Path runtime,ObjectMapper json,JsonNode config){
        var result=json.createObjectNode();if(!config.hasNonNull("recipe"))return result;
        try{
            var source=readJson(json,inside(root,runtime,config.path("recipe").asText()));
            number(source.path("generation"),"originals",result,"generationOriginals");number(source.path("generation"),"segments",result,"generationSegments");
            number(source.path("training").path("bge"),"epochs",result,"epochsBge");number(source.path("training").path("m3"),"epochs",result,"epochsM3");
            number(source.path("formalMinimums"),"effectiveBatch",result,"effectiveBatch");number(source.path("formalMinimums"),"correspondencePairs",result,"minimumPairs");number(source.path("formalMinimums"),"retrievalGroups",result,"minimumRetrievalGroups");
            var training=result.putObject("training");
            for(String family:List.of("bge","m3"))copyScalars(source.path("training").path(family),training.putObject(family),Set.of("epochs","microbatch","effectiveQueries","effectivePairs","maxTokensPerSide","maxJointTokens","explicitNegatives","learningRate","loraR","loraAlpha","dropout","adapterLearningRate","headLearningRate"));
        }catch(Exception error){result.put("availability","READ_ERROR");}
        return result;
    }
}
