package local.campus.review.common;
import com.fasterxml.jackson.databind.*;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;
import java.util.*;

public final class JsonSupport {
    private JsonSupport() {}
    public static String encode(ObjectMapper json,Object value){try{return json.writeValueAsString(value);}catch(Exception e){throw new IllegalArgumentException("Invalid structured data",e);}}
    public static JsonNode parse(ObjectMapper json,String value){try{return json.readTree(value);}catch(Exception e){throw new IllegalStateException("Stored structured data is invalid",e);}}
    public static String hash(ObjectMapper json,Object value){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(encode(json,sorted(json,json.valueToTree(value))).getBytes(StandardCharsets.UTF_8)));}catch(Exception e){throw new IllegalArgumentException("Invalid structured data",e);}}
    private static JsonNode sorted(ObjectMapper json,JsonNode value){
        if(value.isObject()){var result=json.createObjectNode();var keys=new TreeSet<String>();value.fieldNames().forEachRemaining(keys::add);for(var key:keys)result.set(key,sorted(json,value.get(key)));return result;}
        if(value.isArray()){var result=json.createArrayNode();value.forEach(item->result.add(sorted(json,item)));return result;}return value;
    }
}
