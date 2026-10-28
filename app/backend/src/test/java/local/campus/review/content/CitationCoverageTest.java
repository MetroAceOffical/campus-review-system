package local.campus.review.content;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.RuntimeSettings;
import org.junit.jupiter.api.Test;
import java.util.List;
import static local.campus.review.content.DocumentModels.*;
import static org.junit.jupiter.api.Assertions.*;

class CitationCoverageTest {
    @Test void correctInternalCoverageOnlySuppressesItsOwnSupportedEvidence() throws Exception {
        var json=new ObjectMapper();var codec=new DocumentCodec(json,new RuntimeSettings(json));var service=new CitationService(null,json,codec);
        var content=json.readTree("""
          {"type":"doc","content":[{"type":"paragraph","attrs":{"nodeId":"p1"},"content":[
          {"type":"text","text":"😀开头"},{"type":"text","text":"对应来源的四十个字符正文内容用于说明片段引用的覆盖和来源核对不能影响其他段落的检查结果。","marks":[{"type":"citation","attrs":{"sourceIds":["s1"]}}]},
          {"type":"text","text":"其他未引用正文。"}]}]}
          """);
        var document=codec.validateAndExtract(new DocumentInput("引用检查","2",content,List.of(new Source("s1","","INTERNAL","12","21","原稿"))));
        int start=document.citations().getFirst().plainStart(),end=document.citations().getFirst().plainEnd();assertEquals(3,start);
        var evidence=json.readTree("""
          [{"evidenceType":"TEXT_SIMILARITY","sourceWorkId":"12","acceptedCandidate":true,"matches":[],"semanticWindows":[]}]
          """);
        ((com.fasterxml.jackson.databind.node.ArrayNode)evidence.get(0).get("matches")).addObject().put("queryStart",start).put("queryEnd",end);
        service.annotate(evidence,document);assertTrue(evidence.get(0).path("fullyCited").asBoolean());assertTrue(evidence.get(0).path("acceptedCandidate").asBoolean());
        ((com.fasterxml.jackson.databind.node.ObjectNode)evidence.get(0)).put("sourceWorkId","13");service.annotate(evidence,document);assertFalse(evidence.get(0).path("fullyCited").asBoolean());assertEquals("SOURCE_MISMATCH",evidence.get(0).path("citationChecks").get(0).path("status").asText());
        ((com.fasterxml.jackson.databind.node.ObjectNode)evidence.get(0)).put("sourceWorkId","12");((com.fasterxml.jackson.databind.node.ObjectNode)evidence.get(0).get("matches").get(0)).put("queryEnd",end+3);service.annotate(evidence,document);assertFalse(evidence.get(0).path("fullyCited").asBoolean());
        var external=codec.validateAndExtract(new DocumentInput("引用检查","2",content,List.of(new Source("s1","https://example.org/article","EXTERNAL",null,null,"站外"))));service.annotate(evidence,external);assertEquals("EXTERNAL_REVIEW",evidence.get(0).path("citationChecks").get(0).path("status").asText());assertFalse(evidence.get(0).path("fullyCited").asBoolean());
        var semantic=json.readTree("""
          [{"evidenceType":"TEXT_SIMILARITY","sourceWorkId":"12","acceptedCandidate":false,"matches":[],"semanticSummary":{"suspectedReuse":true},"semanticWindows":[{"queryStart":3,"queryEnd":35,"sourceStart":0,"sourceEnd":32,"score":0.9,"tfidfScore":0.6},{"queryStart":35,"queryEnd":47,"sourceStart":32,"sourceEnd":45,"score":0.8,"tfidfScore":0.6},{"queryStart":0,"queryEnd":3,"sourceStart":50,"sourceEnd":53,"score":0.1,"tfidfScore":0.1}]}]
          """);
        service.annotate(semantic,document);assertTrue(semantic.get(0).path("fullyCited").asBoolean());assertEquals(3,semantic.get(0).path("semanticWindows").size());
        assertEquals("1",codec.validateAndExtract(new DocumentInput("旧稿","1",json.readTree("{\"type\":\"doc\",\"content\":[]}"),List.of())).schemaVersion());
    }
}
