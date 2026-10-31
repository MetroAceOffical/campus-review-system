package local.campus.review.workbench;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class TrainingAnalyticsTest {
 @Test void separatesValidationThresholdsFromTestAndKeepsEmptyBinsMissing()throws Exception{
  var json=new ObjectMapper();var rows=new ArrayList<com.fasterxml.jackson.databind.JsonNode>();
  rows.add(json.readTree("{\"sentence1\":\"正常稿\",\"sentence2\":\"独立报道\",\"label\":0,\"predicted\":1,\"score\":0.7,\"scoreType\":\"probability\"}"));
  rows.add(json.readTree("{\"sentence1\":\"复用稿\",\"sentence2\":\"复用稿\",\"label\":1,\"predicted\":1,\"score\":1,\"scoreType\":\"probability\"}"));
  var validation=TrainingAnalyticsService.summarize(json,rows,"validation");
  assertEquals(2,validation.path("count").asInt());assertEquals(1,validation.path("confusionMatrix").get(0).get(1).asInt());
  assertFalse(validation.path("thresholdSweep").isEmpty());assertTrue(validation.path("reliability").get(0).path("observed").isNull());
  assertEquals(1,validation.path("histogram").get(9).path("positive").asInt());
  assertTrue(TrainingAnalyticsService.summarize(json,rows,"test").path("thresholdSweep").isEmpty());
  var saved=json.readTree("{\"taskType\":\"TRAINING\",\"artifacts\":{\"predictions.jsonl\":\"same-sha\"},\"validation\":{\"roc_auc\":0.9166666666666669}}");
  var disk=json.readTree("{\"taskType\":\"TRAINING\",\"artifacts\":{\"predictions.jsonl\":\"same-sha\"},\"validation\":{\"roc_auc\":0.9166666666666667}}");
  assertTrue(TrainingAnalyticsService.sameArtifactIdentity(disk,saved));((com.fasterxml.jackson.databind.node.ObjectNode)disk.path("artifacts")).put("predictions.jsonl","changed-sha");assertFalse(TrainingAnalyticsService.sameArtifactIdentity(disk,saved));
  var margin=new ArrayList<com.fasterxml.jackson.databind.JsonNode>();for(var r:rows){var v=r.deepCopy();((com.fasterxml.jackson.databind.node.ObjectNode)v).put("scoreType","margin").put("score",-.5);margin.add(v);}
  assertTrue(TrainingAnalyticsService.summarize(json,margin,"test").path("reliability").isEmpty());
  assertThrows(RuntimeException.class,()->TrainingAnalyticsService.summarize(json,List.of(json.readTree("{\"label\":1,\"predicted\":1,\"score\":1.1,\"scoreType\":\"probability\"}")),"test"));
 }
}
