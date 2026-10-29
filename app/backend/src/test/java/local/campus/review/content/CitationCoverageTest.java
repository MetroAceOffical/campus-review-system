package local.campus.review.content;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.RuntimeSettings;
import org.junit.jupiter.api.Test;
import java.util.List;
import static local.campus.review.content.DocumentModels.*;
import static org.junit.jupiter.api.Assertions.*;

class CitationCoverageTest {
    @Test void corroboratingSupportRequiresItsOwnCitationCoverage() throws Exception {
        var json=new ObjectMapper();var codec=new DocumentCodec(json,new RuntimeSettings(json));var service=new CitationService(null,json,codec);
        String anchor="在数媒、创意设计、电影电视制作和数字音乐等方向，他们持续积累专业基础，也逐渐熟悉新的制作工具及创作方式。",context="在南传国际，学生的国际化视野是在一节节课程中逐步建立起来的。";
        var content=json.createObjectNode().put("type","doc");var paragraph=content.putArray("content").addObject().put("type","paragraph");paragraph.putObject("attrs").put("nodeId","anchor");var nodes=paragraph.putArray("content");
        var first=nodes.addObject().put("type","text").put("text",anchor);first.putArray("marks").addObject().put("type","citation").putObject("attrs").putArray("sourceIds").add("s1");var second=nodes.addObject().put("type","text").put("text",context);
        var sources=List.of(new Source("s1","","INTERNAL","12","21","原稿"));var evidence=json.createArrayNode();var item=evidence.addObject().put("evidenceType","TEXT_SIMILARITY").put("sourceWorkId","12").put("acceptedCandidate",false);item.putArray("matches");item.putObject("semanticSummary").put("suspectedReuse",true).put("selectionMethod","anchored-context-v1");var windows=item.putArray("semanticWindows");
        int a=DocumentCodec.points(anchor),b=DocumentCodec.points(context);
        windows.addObject().put("queryStart",0).put("queryEnd",a).put("sourceStart",100).put("sourceEnd",139).put("queryText",anchor).put("sourceText","他们不仅在数字媒体、创意设计、影视制作、数字音乐等专业领域内打下了坚实的基础，").put("score",.553).put("tfidfScore",.408).put("citationSupport",true);
        windows.addObject().put("queryStart",a).put("queryEnd",a+b).put("sourceStart",0).put("sourceEnd",40).put("queryText",context).put("sourceText","南传国际的每一堂课仿佛是一块精心雕琢的拼图，逐渐构建起学生对全球视野的深刻理解。").put("score",.628).put("tfidfScore",.170).put("citationSupport",true);
        service.annotate(evidence,codec.validateAndExtract(new DocumentInput("联合证据引用","2",content,sources)));assertFalse(item.path("fullyCited").asBoolean(),"联合判定使用的上下文同样需要独立引用覆盖");
        second.set("marks",first.get("marks").deepCopy());service.annotate(evidence,codec.validateAndExtract(new DocumentInput("联合证据引用","2",content,sources)));assertTrue(item.path("fullyCited").asBoolean());
    }

    @Test void quotedParagraphSeparatorIsNotUncitedArticleContent() throws Exception {
        var json=new ObjectMapper();var codec=new DocumentCodec(json,new RuntimeSettings(json));var service=new CitationService(null,json,codec);
        var content=json.createObjectNode().put("type","doc");var blocks=content.putArray("content");
        for(String text:List.of("😀师生围绕采访准备和新闻资料整理开展交流，逐项讨论信息核实、选题安排以及现场沟通的具体方法。","各小组随后完成录音整理和采访记录核对，将需要补充的背景材料集中登记，并向编辑提交完整的工作说明。")){
            var block=blocks.addObject().put("type","paragraph");block.putObject("attrs").put("nodeId",java.util.UUID.randomUUID().toString());var textNode=block.putArray("content").addObject().put("type","text").put("text",text);textNode.putArray("marks").addObject().put("type","citation").putObject("attrs").putArray("sourceIds").add("s1");
        }
        var document=codec.validateAndExtract(new DocumentInput("整段正确引用","2",content,List.of(new Source("s1","","INTERNAL","12","21","原稿"))));
        var evidence=json.createArrayNode();var item=evidence.addObject().put("evidenceType","TEXT_SIMILARITY").put("sourceWorkId","12").put("acceptedCandidate",true);item.putArray("semanticWindows");item.putArray("matches").addObject().put("queryStart",0).put("queryEnd",DocumentCodec.points(document.plainText()));
        service.annotate(evidence,document);assertTrue(item.path("fullyCited").asBoolean(),"引用跨段时，自动换行不是未引用内容");
    }
    @Test void uncitedRepeatedSemanticOccurrenceMustNotBeClearedByTheCitedFirstCopy() throws Exception {
        var json=new ObjectMapper();var codec=new DocumentCodec(json,new RuntimeSettings(json));var service=new CitationService(null,json,codec);
        String first="师生围绕采访材料核实和报道选题讨论了具体工作方法，并完成现场采访准备。",second="学生随后整理录音并逐项检查引用事实及相关背景材料，形成完整的资料核对记录。",copy=first+second;
        var content=json.createObjectNode().put("type","doc");var paragraph=content.putArray("content").addObject().put("type","paragraph");paragraph.putObject("attrs").put("nodeId","repeat");var nodes=paragraph.putArray("content");
        var cited=nodes.addObject().put("type","text").put("text",copy);cited.putArray("marks").addObject().put("type","citation").putObject("attrs").putArray("sourceIds").add("s1");
        nodes.addObject().put("type","text").put("text",copy);
        var source=List.of(new Source("s1","","INTERNAL","12","21","原稿"));var document=codec.validateAndExtract(new DocumentInput("重复片段引用","2",content,source));
        var evidence=json.createArrayNode();var item=evidence.addObject().put("evidenceType","TEXT_SIMILARITY").put("sourceWorkId","12").put("acceptedCandidate",false);item.putArray("matches");item.putObject("semanticSummary").put("suspectedReuse",true).put("scoreThreshold",.5).put("lexicalFloor",.25);var windows=item.putArray("semanticWindows");
        String sourceFirst="记者和师生共同研究采访事实核对、选题安排与资料审查的方法。",sourceSecond="各小组完成录音整理后，依次复查文中引述的事实与背景材料。";
        int length=copy.codePointCount(0,copy.length()),a=first.codePointCount(0,first.length()),b=second.codePointCount(0,second.length()),c=sourceFirst.codePointCount(0,sourceFirst.length()),d=sourceSecond.codePointCount(0,sourceSecond.length());assertTrue(length>=64);
        for(int offset:List.of(0,length)){
            windows.addObject().put("queryStart",offset).put("queryEnd",offset+a).put("sourceStart",0).put("sourceEnd",c).put("queryText",first).put("sourceText",sourceFirst).put("score",.9).put("tfidfScore",.6);
            windows.addObject().put("queryStart",offset+a).put("queryEnd",offset+a+b).put("sourceStart",c).put("sourceEnd",c+d).put("queryText",second).put("sourceText",sourceSecond).put("score",.8).put("tfidfScore",.6);
        }
        service.annotate(evidence,document);
        assertFalse(item.path("fullyCited").asBoolean(),"未引用的第二次出现仍需提示，不能因来源位置重叠而忽略");
        assertEquals(4,item.path("citationChecks").size());assertEquals(2,item.path("citationVerifiedSegments").asInt());
        assertEquals(4,windows.size());assertTrue(item.path("semanticSummary").path("suspectedReuse").asBoolean());
        ((com.fasterxml.jackson.databind.node.ObjectNode)nodes.get(1)).set("marks",cited.get("marks").deepCopy());
        var both=codec.validateAndExtract(new DocumentInput("重复片段引用","2",content,source));service.annotate(evidence,both);assertTrue(item.path("fullyCited").asBoolean());
    }

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
