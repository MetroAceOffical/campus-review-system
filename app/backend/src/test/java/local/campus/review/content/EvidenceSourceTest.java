package local.campus.review.content;
import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class EvidenceSourceTest {
    @Test void sourceMustMatchTheEvidenceRevisionRatherThanTheLatest()throws Exception{
        var json=new ObjectMapper();var evidence=json.readTree("{\"sourceWorkId\":\"1\",\"sourceRevisionId\":\"2\",\"sourceKind\":\"BODY\"}");
        var library=json.readTree("{\"documents\":[{\"sourceWorkId\":\"1\",\"sourceRevisionId\":\"3\",\"text\":\"new\"},{\"sourceWorkId\":\"1\",\"sourceRevisionId\":\"2\",\"text\":\"old\"}]}");
        assertEquals("old",EvidenceSourceService.findSource(evidence,library).path("text").asText());
        assertThrows(ApiException.class,()->EvidenceSourceService.findSource(json.readTree("{\"sourceWorkId\":\"9\",\"sourceRevisionId\":\"2\"}"),library));
    }
}
