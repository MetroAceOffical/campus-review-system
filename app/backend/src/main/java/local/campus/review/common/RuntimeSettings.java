package local.campus.review.common;

import com.fasterxml.jackson.databind.*;
import org.springframework.stereotype.Component;
import java.nio.file.*;

@Component
public class RuntimeSettings {
    private final Path root,runtime;
    private final JsonNode config;
    public RuntimeSettings(ObjectMapper json) throws Exception {
        root=Path.of(System.getenv().getOrDefault("CAMPUS_ROOT",".")).toAbsolutePath().normalize();
        var local=root.resolve("app/config/local.json");
        config=json.readTree(Files.readString(Files.exists(local)?local:root.resolve("app/config/local.example.json")));
        var configured=root.resolve(config.path("runtimeRoot").asText()).normalize();
        runtime="test".equals(System.getenv("CAMPUS_RUNTIME_NAMESPACE"))?configured.resolve("test"):configured;
        if(runtime.equals(root) || !runtime.startsWith(root))throw new IllegalStateException("Runtime must stay within this project");
    }
    public Path root(){return root;}
    public Path ocrConfiguration(){String name=switch(config.path("ocrProfile").asText("baseline")){case "baseline"->"frozen-ocr.json";case "adaptive"->"frozen-ocr-v2.json";default->throw new IllegalStateException("Unknown OCR profile");};return root.resolve("app/config/"+name);}
    public Path documentConfiguration(){return root.resolve("app/config/frozen-document-models-v1.json");}
    public Path runtime(){return runtime;}
    public Path experiments(){return root.resolve(config.path("runtimeRoot").asText()).normalize().resolve("experiments");}
    public Path python(){return root.resolve(config.path("python").asText()).normalize();}
    public int limit(String name){return config.path("limits").path(name).asInt();}
    public JsonNode limits(){return config.path("limits").deepCopy();}
    public int port(String name){return Integer.parseInt(System.getenv().getOrDefault("CAMPUS_"+name.toUpperCase()+"_PORT",config.path("ports").path(name).asText()));}
    public int timeout(String name){return config.path("timeoutsSeconds").path(name).asInt();}
}
