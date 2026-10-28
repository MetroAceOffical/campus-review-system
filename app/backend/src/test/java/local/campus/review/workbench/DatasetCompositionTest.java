package local.campus.review.workbench;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class DatasetCompositionTest {
    @Test void validatesBoundedUniqueDatasetVersions(){
        String dataset=UUID.randomUUID().toString(),version=UUID.randomUUID().toString();
        assertThrows(ApiException.class,()->DatasetCompositionService.validateSources(List.of(new DatasetCompositionService.Source(dataset,version))));
        assertThrows(ApiException.class,()->DatasetCompositionService.validateSources(List.of(new DatasetCompositionService.Source(dataset,version),new DatasetCompositionService.Source(dataset,UUID.randomUUID().toString()))));
        assertDoesNotThrow(()->DatasetCompositionService.validateSources(List.of(new DatasetCompositionService.Source(dataset,version),new DatasetCompositionService.Source(UUID.randomUUID().toString(),UUID.randomUUID().toString()))));
    }
    @Test void creatorCannotComposeDatasets(){
        var data=new DatasetService(null,null,new ObjectMapper(),new org.springframework.jdbc.datasource.DataSourceTransactionManager());
        var actor=new CurrentUser("1","创作者",CurrentUser.Role.MEMBER,Set.of(),List.of());
        assertEquals("ACCESS_DENIED",assertThrows(ApiException.class,()->new DatasetCompositionService(data).create(actor,null)).code);
    }
}
