package local.campus.review.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class TrainingPermissionTest {
    final CurrentUser reviewer = actor(CurrentUser.Role.REVIEWER), admin = actor(CurrentUser.Role.ADMIN);
    final DatasetService data = new DatasetService(new JdbcTemplate(), null, new ObjectMapper(), new DataSourceTransactionManager()) {
        @Override Map<String,Object> dataset(CurrentUser user,String id) { role(user); throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到数据"); }
    };
    static CurrentUser actor(CurrentUser.Role role) { return new CurrentUser("1","用户",role,Set.of(),List.of()); }
    TrainingService.Start request(String action,String resume) { return new TrainingService.Start("missing","missing",action,null,null,"bert",null,null,null,resume); }
    @Test void reviewerCannotPrepareGenerateTrainOrResumeButCanUsePredictionAndEvaluation() {
        var training = new TrainingService(data);
        for(String action:List.of("PREPARE","GENERATE","TRAIN")) {
            assertEquals(403,assertThrows(ApiException.class,()->training.start(reviewer,request(action,null))).status);
            assertEquals(404,assertThrows(ApiException.class,()->training.start(admin,request(action,null))).status);
        }
        assertEquals(403,assertThrows(ApiException.class,()->training.start(reviewer,request("TRAIN","old-run"))).status);
        for(String action:List.of("PREDICT","EVALUATE"))assertEquals(404,assertThrows(ApiException.class,()->training.start(reviewer,request(action,null))).status);
    }
    @Test void reviewerCannotCreateRetryOrControlTrainingPipelines() {
        var pipelines = new AutomaticPipelineService(data,new TrainingService(data),null,false);
        assertEquals(403,assertThrows(ApiException.class,()->pipelines.create(reviewer,null)).status);
        for(boolean retry:List.of(true,false))assertEquals(403,assertThrows(ApiException.class,()->pipelines.control(reviewer,"missing",retry)).status);
        assertEquals(400,assertThrows(ApiException.class,()->pipelines.create(admin,null)).status);
    }
}
