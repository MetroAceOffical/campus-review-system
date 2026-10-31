package local.campus.review.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class SixModelBundleTest {
    final ObjectMapper json=new ObjectMapper();
    @Test void rawGroupExposesItsOwnInputVersionBeforeCleaning(){
        var data=new DatasetService(null,null,json,null);
        var service=new AutomaticPipelineService(data,null,null,false);
        var row=new HashMap<String,Object>(Map.of("id","group","dataset_id","news","input_version_id","raw-version","name","新闻组","status","QUEUED","updated_at","2026-10-31","state_json",AutomaticPipelineService.initial(json,true,"raw-version").toString()));
        assertEquals("raw-version",service.view(row).path("inputVersionId").asText());
    }
    @Test void newTrainingRequiresExactlyTheSixFamilies(){
        var models=TrainingService.FAMILIES.stream().map(f->new AutomaticPipelineService.Model(f,null)).toList();
        assertDoesNotThrow(()->AutomaticPipelineService.validateModels(models));
        assertThrows(ApiException.class,()->AutomaticPipelineService.validateModels(models.subList(0,5)));
        assertThrows(ApiException.class,()->AutomaticPipelineService.validateModels(List.of(new AutomaticPipelineService.Model("bert",null))));
    }
    @Test void completionWaitsForAllSixIndependentEvaluations(){
        var config=json.createObjectNode().put("evaluate",true);var families=config.putArray("models");
        for(var family:List.of("lr","svm","rf","cnn","bilstm","bert"))families.addObject().put("family",family);
        var state=AutomaticPipelineService.initial(json,false,"version").put("stage","TRAIN");
        for(int i=0;i<6;i++){
            AutomaticPipelineService.consume(state,config,json.createObjectNode(),Map.of("id","model-"+i));
            assertEquals("EVALUATE",state.path("stage").asText());
            assertEquals(i+1,state.path("models").size());
            AutomaticPipelineService.consume(state,config,json.createObjectNode(),Map.of("id","evaluation-"+i));
            assertEquals(i==5?"DONE":"TRAIN",state.path("stage").asText());
        }
        assertEquals(6,state.path("models").size());
        assertEquals("evaluation-5",state.path("models").get(5).path("evaluationRunId").asText());
    }
}
