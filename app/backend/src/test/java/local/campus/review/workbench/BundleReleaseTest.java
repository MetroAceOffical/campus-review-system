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

class BundleReleaseTest {
    final String id="12345678-1234-1234-1234-123456789012";
    @Test void reviewerCannotPublishTrainingGroup(){
        var service=new ReleaseService(null,null,null,null);
        var actor=new CurrentUser("2","审核员",CurrentUser.Role.REVIEWER,Set.of(),List.of());
        assertEquals(403,assertThrows(ApiException.class,()->service.createBundle(actor,new ReleaseService.BundleCreate("0",id,"六模型组"))).status);
    }
    @Test void partialGroupCannotBecomeRelease(){
        var db=mock(JdbcTemplate.class);when(db.queryForList("SELECT * FROM ml_pipeline WHERE id=?",id)).thenReturn(List.of(new HashMap<>(Map.of("bundle_version",1,"status","RUNNING","archived",false))));
        var data=new DatasetService(db,null,new ObjectMapper(),new DataSourceTransactionManager());
        var actor=new CurrentUser("1","管理员",CurrentUser.Role.ADMIN,Set.of(),List.of());
        var service=new ReleaseService(data,null,null,null);
        assertEquals("BUNDLE_INCOMPLETE",assertThrows(ApiException.class,()->service.createBundle(actor,new ReleaseService.BundleCreate("0",id,"六模型组"))).code);
        verify(db,never()).update(anyString(),any(Object[].class));
    }
}
