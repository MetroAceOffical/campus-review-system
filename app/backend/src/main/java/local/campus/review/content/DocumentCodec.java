package local.campus.review.content;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import local.campus.review.common.ApiException;
import org.springframework.stereotype.Component;
import java.net.URI;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static local.campus.review.content.DocumentModels.*;

@Component
public class DocumentCodec {
    private final ObjectMapper json;
    private final local.campus.review.common.RuntimeSettings settings;
    public DocumentCodec(ObjectMapper json,local.campus.review.common.RuntimeSettings settings) {this.json=json;this.settings=settings;}
    public ExtractedDocument validateAndExtract(DocumentInput input) {return extract(input,false);}
    public ExtractedDocument validateForSubmission(DocumentInput input) {return extract(input,true);}
    private ExtractedDocument extract(DocumentInput input,boolean complete) {
        if(input==null || input.title()==null || !"1".equals(input.schemaVersion()) || input.content()==null || !input.content().isObject() || !"doc".equals(input.content().path("type").asText())) invalid("文档结构或版本无效");
        if(points(input.title())>settings.limit("titleCodePoints")) oversized("标题超过字符上限");
        var content=(ObjectNode)input.content().deepCopy();
        var state=new Extraction(complete);
        state.walk(content,"ROOT",0);
        if(points(state.text.toString())>settings.limit("bodyCodePoints")) oversized("正文超过字符上限");
        if(state.images.size()>settings.limit("images")) oversized("配图超过数量上限");
        var sources=input.sources()==null ? List.<Source>of() : List.copyOf(input.sources());
        if(sources.size()>100) invalid("正文来源过多");
        var sourceIds=new HashSet<String>();
        for(var source:sources) {
            if(source==null || !validId(source.sourceId()) || !sourceIds.add(source.sourceId())) invalid("来源编号重复或无效");
            checkUrl(source.url(),!complete);
        }
        if(complete && (input.title().isBlank() || (state.text.toString().isBlank() && state.images.isEmpty()))) invalid("请填写标题，并添加正文或配图");
        var normalized=new DocumentInput(input.title(),"1",content,sources);
        try {
            String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(json.writeValueAsString(sorted(json.valueToTree(normalized))).getBytes(StandardCharsets.UTF_8)));
            return new ExtractedDocument(normalized,state.text.toString(),List.copyOf(state.positions),List.copyOf(state.images),hash,"1","1");
        } catch(java.security.NoSuchAlgorithmException|com.fasterxml.jackson.core.JsonProcessingException e) {throw new IllegalStateException(e);}
    }
    private JsonNode sorted(JsonNode value) {
        if(value.isObject()) {var result=json.createObjectNode();var keys=new TreeSet<String>();value.fieldNames().forEachRemaining(keys::add);for(var key:keys)result.set(key,sorted(value.get(key)));return result;}
        if(value.isArray()) {var result=json.createArrayNode();value.forEach(v->result.add(sorted(v)));return result;}
        return value;
    }
    public static int points(String value) {return value.codePointCount(0,value.length());}
    private static boolean validId(String value) {return value!=null && value.matches("[A-Za-z0-9_-]{1,64}");}
    public void checkUrl(String value,boolean optional) {
        if(value==null || value.isBlank()) {if(!optional)invalid("引用内容请填写来源链接");return;}
        if(value.length()>settings.limit("urlCharacters")) invalid("来源链接过长");
        try {var uri=URI.create(value);if(!Set.of("http","https").contains(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null)invalid("链接仅支持有效的http或https地址");}
        catch(IllegalArgumentException e) {invalid("来源链接无效");}
    }
    private static void invalid(String message) {throw new ApiException(400,"VALIDATION_ERROR",message);}
    private static void oversized(String message) {throw new ApiException(413,"CONTENT_TOO_LARGE",message);}
    private class Extraction {
        final boolean complete;
        final StringBuilder text=new StringBuilder();
        final List<Position> positions=new ArrayList<>();
        final List<ImageNode> images=new ArrayList<>();
        final Set<String> nodeIds=new HashSet<>();
        int blocks=0,nodes=0;
        Extraction(boolean complete){this.complete=complete;}
        ObjectNode attrs(ObjectNode node,Set<String> allowed,boolean identity) {
            if(node.has("attrs") && !node.get("attrs").isObject())invalid("节点属性无效");
            var attrs=node.has("attrs") ? (ObjectNode)node.get("attrs") : json.createObjectNode();
            attrs.fieldNames().forEachRemaining(key->{if(!allowed.contains(key))invalid("不支持的节点属性");});
            if(identity) {
                if(!attrs.hasNonNull("nodeId") || attrs.path("nodeId").asText().isBlank())attrs.put("nodeId",UUID.randomUUID().toString());
                if(!validId(attrs.path("nodeId").asText()) || !nodeIds.add(attrs.path("nodeId").asText()))invalid("文档节点编号重复或无效");
            }
            if(!attrs.isEmpty())node.set("attrs",attrs);
            return attrs;
        }
        void walk(ObjectNode node,String parent,int depth) {
            if(++nodes>30000 || depth>30)invalid("文档层级或节点过多");
            String type=node.path("type").asText();
            if(!Set.of("doc","paragraph","heading","text","bulletList","orderedList","listItem","blockquote","hardBreak","campusImage").contains(type))throw new ApiException(400,"UNSUPPORTED_DOCUMENT_NODE","文档含不支持的内容类型");
            node.fieldNames().forEachRemaining(key->{if(!Set.of("type","attrs","content","text","marks").contains(key))invalid("文档含不支持的字段");});
            if(!"text".equals(type) && (node.has("text") || node.has("marks")))invalid("非文字节点不能携带文字或格式属性");
            if("doc".equals(type) && !"ROOT".equals(parent))invalid("文档根节点不能嵌套");
            boolean inline=Set.of("text","hardBreak").contains(type);
            if(inline && !Set.of("paragraph","heading").contains(parent))invalid("文字节点位置无效");
            if(Set.of("paragraph","heading").contains(parent) && !inline)invalid("段落中只能包含文字或换行");
            if(Set.of("bulletList","orderedList").contains(parent) && !"listItem".equals(type))invalid("列表结构无效");
            if("listItem".equals(type) && !Set.of("bulletList","orderedList").contains(parent))invalid("列表项位置无效");
            if("campusImage".equals(type)) {
                var a=attrs(node,Set.of("nodeId","fileId","caption","origin","sourceUrl"),true);
                if(!a.path("fileId").asText().matches("[1-9][0-9]{0,18}"))invalid("图片文件编号无效");
                String origin=a.path("origin").asText("");
                if(!origin.isEmpty() && !Set.of("ORIGINAL","CITED").contains(origin))invalid("请选择有效的图片来源");
                if(complete && origin.isEmpty())invalid("请选择图片原创或引用");
                String url=a.path("sourceUrl").asText("");checkUrl(url,!complete || !"CITED".equals(origin));
                if(points(a.path("caption").asText(""))>1000)invalid("图注过长");
                images.add(new ImageNode(a.path("nodeId").asText(),a.path("fileId").asText(),a.path("caption").asText(""),origin,url));
                if(images.size()>settings.limit("images"))oversized("配图超过数量上限");
                if(node.has("content") || node.has("text") || node.has("marks"))invalid("图片不能携带正文子节点");
                return;
            }
            if(Set.of("paragraph","heading").contains(type)) {
                var a=attrs(node,"heading".equals(type)?Set.of("nodeId","level"):Set.of("nodeId"),true);
                if("heading".equals(type) && !Set.of(2,3).contains(a.path("level").asInt()))invalid("仅支持二三级标题");
                if(blocks++>0)text.append('\n');
                int offset=0;
                if(node.has("content") && !node.get("content").isArray())invalid("段落内容无效");
                for(var child:node.path("content")) {
                    if(!child.isObject())invalid("子节点无效");
                    walk((ObjectNode)child,type,depth+1);
                    String value="hardBreak".equals(child.path("type").asText()) ? "\n" : child.path("text").asText("").replace("\r\n","\n").replace('\r','\n');
                    if(child.has("text"))((ObjectNode)child).put("text",value);
                    int start=points(text.toString()),length=points(value);
                    if(start+length>settings.limit("bodyCodePoints"))oversized("正文超过字符上限");
                    text.append(value);positions.add(new Position(a.path("nodeId").asText(),start,start+length,offset,offset+length));offset+=length;
                }
                if(offset==0) {int start=points(text.toString());positions.add(new Position(a.path("nodeId").asText(),start,start,0,0));}
                return;
            }
            if("text".equals(type)) {
                if(!node.has("text") || !node.get("text").isTextual() || node.has("content"))invalid("文字节点无效");
                attrs(node,Set.of(),false);
                if(node.has("marks") && !node.get("marks").isArray())invalid("文字格式无效");
                for(var mark:node.path("marks")) {
                    if(!mark.isObject() || !Set.of("bold","italic","link").contains(mark.path("type").asText()))invalid("不支持的文字格式");
                    if("link".equals(mark.path("type").asText())) {
                        checkUrl(mark.path("attrs").path("href").asText(),false);
                        var safe=json.createObjectNode().put("href",mark.path("attrs").path("href").asText()).put("target","_blank").put("rel","noopener noreferrer nofollow");((ObjectNode)mark).set("attrs",safe);
                    } else ((ObjectNode)mark).remove("attrs");
                }
                return;
            }
            if("hardBreak".equals(type)) {attrs(node,Set.of(),false);if(node.has("text") || node.has("content"))invalid("换行结构无效");return;}
            var blockAttrs=attrs(node,"orderedList".equals(type)?Set.of("start","type"):Set.of(),false);
            if("orderedList".equals(type)) {
                if(blockAttrs.has("start") && (!blockAttrs.get("start").isIntegralNumber() || blockAttrs.path("start").asInt()<1 || blockAttrs.path("start").asInt()>100000))invalid("列表起始编号无效");
                if(blockAttrs.hasNonNull("type") && !Set.of("1","a","A","i","I").contains(blockAttrs.path("type").asText()))invalid("列表编号格式无效");
            }
            if(node.has("text") || node.has("marks"))invalid("块节点不能携带文字属性");
            if(node.has("content") && !node.get("content").isArray())invalid("块内容无效");
            for(var child:node.path("content")) {if(!child.isObject())invalid("子节点无效");walk((ObjectNode)child,type,depth+1);}
        }
    }
}
