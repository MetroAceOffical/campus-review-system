package local.campus.review.detection;

import com.fasterxml.jackson.databind.*;
import local.campus.review.common.*;
import org.springframework.stereotype.Component;
import java.net.*;
import java.net.http.*;
import java.nio.file.*;
import java.time.Duration;

@Component
public class DetectorClient {
    public static class DetectorFailure extends RuntimeException {
        public final String code;
        public DetectorFailure(String code){super(code);this.code=code;}
    }
    private final RuntimeSettings settings;private final ObjectMapper json;
    private final ThreadLocal<Long> deadline=new ThreadLocal<>();
    private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    public DetectorClient(RuntimeSettings settings,ObjectMapper json){this.settings=settings;this.json=json;}
    public AutoCloseable budget(String name){deadline.set(System.nanoTime()+Duration.ofSeconds(settings.timeout(name)).toNanos());return ()->deadline.remove();}
    public JsonNode health(boolean ocr){try{return exchange(ocr,"/health",null,5);}catch(RuntimeException e){return json.createObjectNode().put("ready",false).put("busy",false).put("errorCode","SERVICE_UNAVAILABLE");}}
    public JsonNode frozenOcrConfig(){try{return json.readTree(Files.readString(settings.root().resolve("app/config/frozen-ocr.json")));}catch(Exception e){throw new DetectorFailure("CONFIG_UNAVAILABLE");}}
    public JsonNode call(boolean ocr,String endpoint,JsonNode input,String timeout){
        var result=exchange(ocr,endpoint,input,settings.timeout(timeout));
        if(!endpoint.equals("/library/build")){
            for(String field:ocr?new String[]{"taskId","attemptId","fileId","fileSha256"}:new String[]{"taskId","attemptId","scene","versionId","inputSnapshotKey","inputSha256","libraryGenerationId","configId"})
                if(!input.path(field).equals(result.path(field)))throw new DetectorFailure("RESULT_IDENTITY_MISMATCH");
        }
        return result;
    }
    private JsonNode exchange(boolean ocr,String endpoint,JsonNode input,int seconds){
        try{
            long nanos=Duration.ofSeconds(seconds).toNanos();if(deadline.get()!=null)nanos=Math.min(nanos,deadline.get()-System.nanoTime());
            if(nanos<=0)throw new DetectorFailure("DETECTOR_TIMEOUT");
            String token=Files.readString(settings.root().resolve("runtime/private-config/internal-token")).trim();
            var request=HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+settings.port(ocr?"ocr":"detector")+endpoint)).timeout(Duration.ofNanos(nanos)).header("X-Internal-Token",token);
            if(input==null)request.GET();else request.header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(JsonSupport.encode(json,input)));
            var response=client.send(request.build(),HttpResponse.BodyHandlers.ofString());var result=json.readTree(response.body());
            if(response.statusCode()!=200)throw new DetectorFailure(result.path("errorCode").asText("DETECTOR_HTTP_ERROR"));
            return result;
        }catch(DetectorFailure e){throw e;}catch(HttpTimeoutException e){throw new DetectorFailure("DETECTOR_TIMEOUT");}catch(Exception e){throw new DetectorFailure("SERVICE_UNAVAILABLE");}
    }
}
