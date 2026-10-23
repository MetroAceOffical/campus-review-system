package local.campus.review.experiment;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;
import local.campus.review.common.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

/** Publishes only a completely verified snapshot; a bad replacement cannot discard it. */
@Component
public class ExperimentCatalog {
    private final Path root;private final ObjectMapper json;
    private Map<String,ObjectNode> active=Map.of();private String warning;
    @Autowired public ExperimentCatalog(RuntimeSettings settings,ObjectMapper json){this(settings.experiments(),json);}
    ExperimentCatalog(Path root,ObjectMapper json){this.root=root.toAbsolutePath().normalize();this.json=json;}
    private String sha(Path path)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));}
    private Path inside(Path base,String relative)throws Exception{
        Path path=base.resolve(relative).normalize();
        if(relative.isBlank()||Path.of(relative).isAbsolute()||!path.startsWith(base)||!path.toRealPath().startsWith(root.toRealPath()))throw new IllegalArgumentException("Unsafe experiment path");
        return path;
    }
    private void refresh(){
        try{
            if(!Files.exists(root.resolve("catalog.json"))&&active.isEmpty()){warning=null;return;}
            var index=json.readTree(Files.readString(root.resolve("catalog.json")));
            if(!"1".equals(index.path("schemaVersion").asText())||!index.path("experiments").isArray())throw new IllegalArgumentException("Unsupported catalog");
            Map<String,ObjectNode> next=new LinkedHashMap<>();
            for(var entry:index.path("experiments")){
                Path manifestPath=inside(root,entry.path("manifest").asText());String hash=sha(manifestPath);
                if(!hash.equals(entry.path("manifestSha256").asText())||!hash.equals(Files.readString(manifestPath.getParent().resolve("READY")).trim()))throw new IllegalArgumentException("Manifest checksum mismatch");
                var manifest=json.readTree(Files.readString(manifestPath));String id=manifest.path("id").asText();
                if(!id.matches("[a-zA-Z0-9_-]+")||!id.equals(entry.path("id").asText())||!"1".equals(manifest.path("schemaVersion").asText())||manifest.path("contentVersion").asText().isBlank()||!manifest.path("testSets").isArray())throw new IllegalArgumentException("Invalid manifest");
                var bundle=json.createObjectNode();bundle.set("manifest",manifest);
                for(String artifact:List.of("metrics","curves","history","search")){
                    String name=artifact+".json";Path path=inside(manifestPath.getParent(),name);
                    if(!sha(path).equals(manifest.path("artifacts").path(name).asText()))throw new IllegalArgumentException("Artifact checksum mismatch: "+name);
                    bundle.set(artifact,json.readTree(Files.readString(path)));
                }
                if(next.put(id,bundle)!=null)throw new IllegalArgumentException("Duplicate experiment");
            }
            active=Collections.unmodifiableMap(next);warning=null;
        }catch(Exception failure){
            warning="新实验包校验失败，保留上次已验证结果";
            if(active.isEmpty())throw new ApiException(503,"EXPERIMENT_PACKAGE_INVALID","实验包不可用，请检查导出与完整性");
        }
    }
    private ObjectNode envelope(){var result=json.createObjectNode().put("lastCheckedAt",Instant.now().toString());if(warning!=null)result.put("warning",warning);return result;}
    public synchronized ObjectNode list(){refresh();var result=envelope();var rows=result.putArray("experiments");active.values().forEach(bundle->rows.add(bundle.path("manifest").deepCopy()));return result;}
    public synchronized ObjectNode bundle(String id){refresh();var found=active.get(id);if(found==null)throw new ApiException(404,"EXPERIMENT_NOT_FOUND","实验不存在");var result=envelope();result.setAll(found.deepCopy());return result;}
    public synchronized ObjectNode part(String id,String part,String testSet){
        var bundle=bundle(id);var manifest=bundle.path("manifest");var result=envelope().put("contentVersion",manifest.path("contentVersion").asText());
        if(part.equals("manifest")){result.set("manifest",manifest);return result;}
        JsonNode values=bundle.path(part);
        if(part.equals("metrics")||part.equals("curves")){
            String selected=testSet==null?manifest.path("testSets").get(0).path("id").asText():testSet;
            boolean allowed=false;for(var set:manifest.path("testSets"))if(set.path("id").asText().equals(selected))allowed=true;
            if(!allowed||!values.path("sets").has(selected))throw new ApiException(400,"TEST_SET_INVALID","测试口径不存在");
            result.put("testSet",selected);values=values.path("sets").path(selected);
        }
        result.set("values",values);return result;
    }
}
