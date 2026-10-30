package local.campus.review.workbench;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class DatasetPurposeTest {
    @Test void restrictsPurposeToCompatibleDatasetKinds(){
        assertEquals("BOTH",DatasetService.purpose("NEWS","BOTH"));
        assertEquals("TRAIN",DatasetService.purpose("PAIRS",null));
        assertEquals("UNSET",DatasetService.purpose("NEWS",null));
        assertThrows(ApiException.class,()->DatasetService.purpose("PAIRS","LIBRARY"));
        assertThrows(ApiException.class,()->DatasetService.purpose("NEWS","other"));
        var json=new com.fasterxml.jackson.databind.ObjectMapper();
        var requested=json.createObjectNode().put("auto_reference_import",true);
        assertTrue(DatasetService.autoImport("NEWS","BOTH",requested));
        assertFalse(DatasetService.autoImport("NEWS","BOTH",json.createObjectNode()));
        assertThrows(ApiException.class,()->DatasetService.autoImport("PAIRS","TRAIN",requested));
    }
}
