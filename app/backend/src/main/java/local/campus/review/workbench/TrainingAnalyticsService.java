package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import org.springframework.stereotype.Service;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.util.*;

/** Read-only summaries of complete, identity-checked validation/test artifacts. */
@Service
public class TrainingAnalyticsService {
 final DatasetService data;final TrainingService training;
 final Map<String,ObjectNode> cache=Collections.synchronizedMap(new LinkedHashMap<>(32,.75f,true){protected boolean removeEldestEntry(Map.Entry<String,ObjectNode> entry){return size()>32;}});
 public TrainingAnalyticsService(DatasetService data,TrainingService training){this.data=data;this.training=training;}
 public JsonNode get(CurrentUser user,String id)throws Exception{
  data.role(user);var task=data.runRow(user,id);String action=task.get("action").toString();
  if(!Set.of("TRAIN","EVALUATE").contains(action)||!"COMPLETED".equals(task.get("status")))throw new ApiException(409,"RESULT_NOT_READY","完成训练或评价后查看分析");
  var manifest=JsonSupport.parse(data.json,Objects.toString(task.get("result_json"),"{}"));
  String partition=action.equals("TRAIN")?"validation":"test",name=action.equals("TRAIN")?"validation-predictions.jsonl":"predictions.jsonl";
  if(!manifest.path("artifacts").has(name)&&action.equals("TRAIN"))return data.json.createObjectNode().put("available",false).put("partition",partition).put("message","该历史任务未保存验证集逐条得分");
  Path output=training.directory(id).resolve("output"),file=output.resolve(name),manifestFile=output.resolve("manifest.json");
  if(!Files.isRegularFile(file)||!Files.isRegularFile(manifestFile)||!file.toRealPath().startsWith(output.toRealPath())||!manifestFile.toRealPath().startsWith(output.toRealPath()))throw changed();
  if(!sameArtifactIdentity(data.json.readTree(Files.readString(manifestFile)),manifest))throw changed();
  String expected=manifest.path("artifacts").path(name).asText();if(!expected.matches("[0-9a-f]{64}"))throw changed();
  long expectedRows=action.equals("TRAIN")?manifest.path("validationRows").asLong(-1):manifest.path("metrics").path("rows").asLong(-1);
  if(expectedRows<1||expectedRows>100000)throw changed();
  String cacheKey=partition+":"+expectedRows+":"+expected;var cached=cache.get(cacheKey);
  if(cached!=null){if(!hash(file).equals(expected))throw changed();return cached.deepCopy().put("runId",id);}
  var rows=new ArrayList<Sample>();var digest=MessageDigest.getInstance("SHA-256");
  try(var input=new DigestInputStream(Files.newInputStream(file),digest);var reader=new BufferedReader(new InputStreamReader(input,StandardCharsets.UTF_8))){
   String line;while((line=TrainingService.predictionLine(reader))!=null){if(rows.size()>=100000||line.isBlank())throw changed();rows.add(sample(data.json.readTree(line)));}
  }
  if(rows.size()!=expectedRows||!HexFormat.of().formatHex(digest.digest()).equals(expected))throw changed();
  var result=aggregate(data.json,rows,partition).put("available",true).put("artifactSha256",expected);cache.put(cacheKey,result);return result.deepCopy().put("runId",id);
 }
 static String hash(Path file)throws Exception{var digest=MessageDigest.getInstance("SHA-256");try(var stream=new DigestInputStream(Files.newInputStream(file),digest)){stream.transferTo(OutputStream.nullOutputStream());}return HexFormat.of().formatHex(digest.digest());}
 static boolean sameArtifactIdentity(JsonNode file,JsonNode saved){
  // MySQL JSON can round floating metrics at the last binary digit. Compare
  // exact artifact/data identities and integer counts, then hash the file bytes.
  for(String key:List.of("taskType","status","artifacts","inputSha256","preparationSha256","modelSha256","trainRows","validationRows","count"))if(!file.path(key).equals(saved.path(key)))return false;
  return file.path("metrics").path("rows").equals(saved.path("metrics").path("rows"));
 }
 record Sample(int label,int predicted,double score,String type,int bucket){}
 static Sample sample(JsonNode row){
  if(row==null||!row.path("label").isIntegralNumber()||!row.path("predicted").isIntegralNumber()||!Set.of(0,1).contains(row.path("label").asInt())||!Set.of(0,1).contains(row.path("predicted").asInt())||!row.path("score").isNumber())throw changed();
  String type=row.path("scoreType").asText();double score=row.path("score").asDouble();if(!Set.of("margin","probability").contains(type)||!Double.isFinite(score)||type.equals("probability")&&(score<0||score>1))throw changed();
  String a=row.path("sentence1").asText(),b=row.path("sentence2").asText();int length=Math.max(a.codePointCount(0,a.length()),b.codePointCount(0,b.length()));
  return new Sample(row.path("label").asInt(),row.path("predicted").asInt(),score,type,length<=64?0:length<=128?1:length<=256?2:length<=512?3:4);
 }
 static ApiException changed(){return new ApiException(409,"ARTIFACT_CHANGED","预测工件不完整或校验失败");}
 static ObjectNode summarize(ObjectMapper json,List<JsonNode> rows,String partition){
  return aggregate(json,rows.stream().map(TrainingAnalyticsService::sample).toList(),partition);
 }
 static ObjectNode aggregate(ObjectMapper json,List<Sample> rows,String partition){
  if(rows.isEmpty()||!Set.of("validation","test").contains(partition))throw changed();
  String type=rows.get(0).type();
  boolean probability=type.equals("probability");double min=probability?0:Double.POSITIVE_INFINITY,max=probability?1:Double.NEGATIVE_INFINITY;
  int[][] matrix=new int[2][2];int[][] lengths=new int[5][4];
  for(var row:rows){
   if(!type.equals(row.type()))throw changed();double score=row.score();
   if(!probability){min=Math.min(min,score);max=Math.max(max,score);}
   int actual=row.label(),predicted=row.predicted();matrix[actual][predicted]++;
   int bucket=row.bucket();lengths[bucket][0]++;
   if(actual!=predicted){lengths[bucket][1]++;lengths[bucket][actual==0?2:3]++;}
  }
  if(min==max){min-=.5;max+=.5;}
  int bins=probability?10:20;int[][] histogram=new int[bins][2];double[][] reliability=new double[10][3];double brier=0;
  for(var row:rows){double s=row.score();int label=row.label();histogram[Math.min(bins-1,Math.max(0,(int)((s-min)/(max-min)*bins)))][label]++;
   if(probability){int bin=Math.min(9,(int)(s*10));reliability[bin][0]++;reliability[bin][1]+=s;reliability[bin][2]+=label;brier+=(s-label)*(s-label);}
  }
  var result=json.createObjectNode().put("partition",partition).put("count",rows.size()).put("scoreType",type).put("savedThreshold",probability?.5:0);
  result.set("confusionMatrix",json.valueToTree(matrix));var hist=result.putArray("histogram");
  for(int i=0;i<bins;i++)hist.addObject().put("lower",min+(max-min)*i/bins).put("upper",min+(max-min)*(i+1)/bins).put("negative",histogram[i][0]).put("positive",histogram[i][1]);
  var reliable=result.putArray("reliability");if(probability){result.put("brierScore",brier/rows.size());for(int i=0;i<10;i++){var bin=reliable.addObject().put("lower",i/10.).put("upper",(i+1)/10.).put("count",(int)reliability[i][0]);if(reliability[i][0]==0){bin.putNull("predicted");bin.putNull("observed");}else{bin.put("predicted",reliability[i][1]/reliability[i][0]);bin.put("observed",reliability[i][2]/reliability[i][0]);}}}
  var errors=result.putArray("lengthErrors");String[] names={"≤64字","65–128字","129–256字","257–512字",">512字"};
  for(int i=0;i<5;i++){var item=errors.addObject().put("bucket",names[i]).put("rows",lengths[i][0]).put("wrong",lengths[i][1]).put("FP",lengths[i][2]).put("FN",lengths[i][3]);if(lengths[i][0]==0)item.putNull("errorRate");else item.put("errorRate",(double)lengths[i][1]/lengths[i][0]);}
  var sweep=result.putArray("thresholdSweep");
  if(partition.equals("validation")){
   // Sort once: sweep 101 displayed thresholds without 101 full passes.
   var ordered=new ArrayList<>(rows);ordered.sort(Comparator.comparingDouble(Sample::score));int positives=(int)rows.stream().filter(r->r.label()==1).count(),negatives=rows.size()-positives,at=0,belowPositive=0,belowNegative=0;
   var thresholds=new TreeSet<Double>();for(int i=0;i<=100;i++)thresholds.add(min+(max-min)*i/100);thresholds.add(probability?.5:0.);
   for(double threshold:thresholds){while(at<ordered.size()&&ordered.get(at).score()<threshold){if(ordered.get(at++).label()==1)belowPositive++;else belowNegative++;}
    int tp=positives-belowPositive,fp=negatives-belowNegative;double precision=tp+fp==0?0:(double)tp/(tp+fp),recall=positives==0?0:(double)tp/positives;
    var point=sweep.addObject().put("threshold",threshold).put("precision",precision).put("recall",recall).put("f1",precision+recall==0?0:2*precision*recall/(precision+recall));if(negatives==0)point.putNull("falsePositiveRate");else point.put("falsePositiveRate",(double)fp/negatives);
   }
  }
  return result;
 }
}
