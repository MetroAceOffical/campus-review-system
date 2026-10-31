package local.campus.review.workbench;
import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.CurrentUser;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.jdbc.core.JdbcTemplate;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class ModelComparisonTest {
    @TempDir Path folder;
    @Test void streamsTheSameRowsAndSeparatesImprovementsFromRegressions()throws Exception{
        var json=new ObjectMapper();var data=new DatasetService(mock(JdbcTemplate.class),null,json,new org.springframework.jdbc.datasource.DataSourceTransactionManager());
        var training=new TrainingService(data){@Override public Path artifact(CurrentUser actor,String run,String name){return folder.resolve(run+".jsonl");}};
        var actor=new CurrentUser("1","管理员",CurrentUser.Role.ADMIN,Set.of(),List.of());var service=spy(new ModelComparisonService(data,training));
        @SuppressWarnings("unchecked") Map<String,Object>[] pair=new Map[]{new HashMap<>(Map.of("id","parent","status","COMPLETED","result_json","{\"preparationSha256\":\"same\"}")),new HashMap<>(Map.of("id","child","status","COMPLETED","result_json","{\"preparationSha256\":\"same\"}"))};doReturn(pair).when(service).pair(actor,"child");
        for(String run:List.of("parent","child")){
            var lines=new ArrayList<String>();for(int i=0;i<3;i++){int prediction=run.equals("parent")?(i==0?0:i==1?1:0):(i==0?1:0);lines.add(json.writeValueAsString(Map.of("id",i,"sentence1","原文"+i,"sentence2","改写"+i,"label",1,"predicted",prediction,"score",prediction==1?.8:.2)));}Files.write(folder.resolve(run+".jsonl"),lines);
        }
        for(int i=0;i<2;i++){String id=pair[i].get("id").toString();pair[i].put("result_json",json.writeValueAsString(Map.of("preparationSha256","same","artifacts",Map.of("predictions.jsonl",TrainingAnalyticsService.hash(folder.resolve(id+".jsonl"))))));}
        var result=service.changes(actor,"child",1,1,"regressed");assertEquals(1,result.path("improved").asInt());assertEquals(1,result.path("regressed").asInt());assertEquals(2,result.path("changed").asInt());assertEquals(1,result.path("total").asInt());assertEquals(1,result.path("items").get(0).path("id").asInt());Files.writeString(folder.resolve("child.jsonl"),"changed");assertThrows(local.campus.review.common.ApiException.class,()->service.changes(actor,"child",1,1,"errors"));
    }
}
