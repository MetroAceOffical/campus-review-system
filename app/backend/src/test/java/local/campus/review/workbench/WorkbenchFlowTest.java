package local.campus.review.workbench;
import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
class WorkbenchFlowTest {
    final ObjectMapper json=new ObjectMapper();
    final JdbcTemplate db=mock(JdbcTemplate.class);
    final DatasetService data=spy(new DatasetService(db,null,json,new DataSourceTransactionManager()));
    final TrainingService training=mock(TrainingService.class);
    final String id="11111111-1111-4111-8111-111111111111",dataset="22222222-2222-4222-8222-222222222222",version="33333333-3333-4333-8333-333333333333";
    CurrentUser user(String id,CurrentUser.Role role){return new CurrentUser(id,"用户",role,Set.of(),List.of());}
    @Test void rejectsRolesForeignOwnersConflictsAndMismatchedObjects(){
        var flows=new WorkbenchFlowService(data,training);
        var admin=user("1",CurrentUser.Role.ADMIN);
        assertEquals(403,assertThrows(ApiException.class,()->flows.create(user("1",CurrentUser.Role.MEMBER),new WorkbenchFlowService.Create(id,"UPLOAD",null))).status);
        assertEquals(403,assertThrows(ApiException.class,()->flows.create(user("1",CurrentUser.Role.REVIEWER),new WorkbenchFlowService.Create(id,"TRAIN",null))).status);
        when(db.queryForList("SELECT * FROM workbench_flow WHERE id=?",id)).thenReturn(List.of(Map.of("id",id,"created_by",2L,"kind","UPLOAD","context_json","{}","revision",1L)));
        assertEquals(404,assertThrows(ApiException.class,()->flows.get(admin,id)).status);
        when(db.queryForList("SELECT * FROM workbench_flow WHERE id=?",id)).thenReturn(List.of(Map.of("id",id,"created_by",1L,"kind","TRAIN","context_json","{}","revision",1L)));
        assertEquals(409,assertThrows(ApiException.class,()->flows.update(admin,id,new WorkbenchFlowService.Edit(0,json.createObjectNode()))).status);
        doReturn(Map.of("id",dataset,"organization_id",1L,"kind","NEWS")).when(data).dataset(admin,dataset);
        doReturn(Map.of("dataset_id","another-dataset","stage","CLEAN")).when(data).version(dataset,version);
        assertEquals(400,assertThrows(ApiException.class,()->flows.validateContext(admin,"TRAIN",json.createObjectNode().put("datasetId",dataset).put("versionId",version))).status);
    }
}
