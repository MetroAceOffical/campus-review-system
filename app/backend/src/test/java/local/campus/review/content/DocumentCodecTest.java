package local.campus.review.content;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.common.ApiException;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static local.campus.review.content.DocumentModels.*;

class DocumentCodecTest {
    final ObjectMapper json=new ObjectMapper();
    DocumentInput input(String content) throws Exception { return new DocumentInput("测试","1",json.readTree(content),List.of()); }
    @Test void unicodeAndFormattingOffsets() throws Exception {
        var codec=new DocumentCodec(json,new local.campus.review.common.RuntimeSettings(json));
        var result=codec.validateAndExtract(input("""
          {"type":"doc","content":[{"type":"paragraph","attrs":{"nodeId":"p1"},"content":[{"type":"text","text":"A😀","marks":[{"type":"bold"}]},{"type":"text","text":"中"}]},{"type":"bulletList","content":[{"type":"listItem","content":[{"type":"paragraph","attrs":{"nodeId":"p2"},"content":[{"type":"text","text":"文"}]}]}]}]}
          """));
        assertEquals("A😀中\n文",result.plainText());
        assertEquals(5,result.plainText().codePointCount(0,result.plainText().length()));
        assertEquals(2,result.positionMap().get(1).plainStart());
        assertEquals(3,result.positionMap().get(1).plainEnd());
        assertEquals(4,result.positionMap().get(2).plainStart());
        assertEquals("p2",result.positionMap().get(2).nodeId());
        assertEquals(2,result.positionMap().get(1).nodeTextStart());
    }
    @Test void picturesKeepFileIdentityAndSourcesOutOfBody() throws Exception {
        var codec=new DocumentCodec(json,new local.campus.review.common.RuntimeSettings(json));
        String image="{\"type\":\"campusImage\",\"attrs\":{\"nodeId\":\"i1\",\"fileId\":\"42\",\"caption\":\"不混入正文\",\"origin\":\"ORIGINAL\",\"sourceUrl\":\"\"}}";
        var result=codec.validateAndExtract(input("{\"type\":\"doc\",\"content\":["+image+"]}"));
        assertEquals("",result.plainText()); assertEquals("42",result.images().getFirst().fileId());
        assertThrows(ApiException.class,()->codec.validateAndExtract(input("{\"type\":\"doc\",\"content\":["+image+","+image+"]}")));
    }
    @Test void unsupportedNodesUnsafeLinksAndOversizeAreRejected() throws Exception {
        var codec=new DocumentCodec(json,new local.campus.review.common.RuntimeSettings(json));
        assertThrows(ApiException.class,()->codec.validateAndExtract(input("{\"type\":\"doc\",\"content\":[{\"type\":\"script\"}]}")));
        assertThrows(ApiException.class,()->codec.validateAndExtract(input("{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"链接\",\"marks\":[{\"type\":\"link\",\"attrs\":{\"href\":\"javascript:alert(1)\"}}]}]}]}")));
        var content=json.createObjectNode().put("type","doc");
        content.putArray("content").addObject().put("type","paragraph").putArray("content").addObject().put("type","text").put("text","😀".repeat(10001));
        assertThrows(ApiException.class,()->codec.validateAndExtract(new DocumentInput("","1",content,List.of())));
        assertDoesNotThrow(()->codec.validateAndExtract(input("{\"type\":\"doc\",\"content\":[]}")));
    }
    @Test void unfinishedSourcesAllowedOnlyForDraft() throws Exception {
        var codec=new DocumentCodec(json,new local.campus.review.common.RuntimeSettings(json));
        var draft=input("{\"type\":\"doc\",\"content\":[{\"type\":\"campusImage\",\"attrs\":{\"nodeId\":\"image\",\"fileId\":\"42\",\"origin\":\"CITED\",\"sourceUrl\":\"\"}}]}");
        assertDoesNotThrow(()->codec.validateAndExtract(draft));
        assertThrows(ApiException.class,()->codec.validateForSubmission(draft));
    }
    @Test void acceptsActualTiptapOrderedListAttributes() throws Exception {
        var codec=new DocumentCodec(json,new local.campus.review.common.RuntimeSettings(json));
        var value=input("{\"type\":\"doc\",\"content\":[{\"type\":\"orderedList\",\"attrs\":{\"start\":1,\"type\":null},\"content\":[{\"type\":\"listItem\",\"content\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"列表正文\"}]}]}]}]}");
        assertEquals("列表正文",codec.validateAndExtract(value).plainText());
    }
}
