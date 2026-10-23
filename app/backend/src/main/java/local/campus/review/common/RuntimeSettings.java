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
        runtime=root.resolve(config.path("runtimeRoot").asText()).normalize();
        if(runtime.equals(root) || !runtime.startsWith(root))throw new IllegalStateException("Runtime must stay within this project");
    }
    public Path root(){return root;}
    public Path runtime(){return runtime;}
    public Path python(){return root.resolve(config.path("python").asText()).normalize();}
    public int limit(String name){return config.path("limits").path(name).asInt();}
    public JsonNode limits(){return config.path("limits").deepCopy();}
}
