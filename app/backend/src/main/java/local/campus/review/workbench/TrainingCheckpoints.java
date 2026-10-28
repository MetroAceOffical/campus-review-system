package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.file.*;
import java.util.*;

final class TrainingCheckpoints {
    private TrainingCheckpoints(){}
    static ObjectNode inspect(DatasetService data,Map<String,Object> run){
        var result=data.json.createObjectNode().put("available",false);
        if(!"TRAIN".equals(run.get("action"))||!Set.of("FAILED","CANCELLED","INTERRUPTED").contains(run.get("status")))return result;
        try{
            var options=data.json.readTree(run.get("options_json").toString());String family=options.path("family").asText();
            if(!Set.of("cnn","bilstm","bert").contains(family)||data.processes.containsKey(run.get("id").toString()))return result;
            Path folder=data.settings.runtime().resolve("workbench/computations").resolve(run.get("id").toString()).resolve("output"),file=folder.resolve("resume.json");
            if(!Files.isRegularFile(file)||Files.size(file)>64000)return result;
            var meta=data.json.readTree(Files.readString(file));String checkpoint=meta.path("checkpointFile").asText();
            if(meta.path("schemaVersion").asInt()!=1||!"WEB_NEURAL_CHECKPOINT".equals(meta.path("taskType").asText())||!Set.of("checkpoint-a.pt","checkpoint-b.pt").contains(checkpoint)||!Files.isRegularFile(folder.resolve(checkpoint))||!meta.path("checkpointSha256").asText().matches("[0-9a-f]{64}")||!family.equals(meta.path("identity").path("family").asText()))return result;
            if(meta.hasNonNull("bestSha256")&&(!meta.path("bestFile").asText().matches("best-epoch-[0-9]{4}\\.pt")||!Files.isRegularFile(folder.resolve(meta.path("bestFile").asText()))))return result;
            var fields=meta.path("identity").path("code").fields();int files=0;while(fields.hasNext()){
                var code=fields.next();Path path=data.settings.root().resolve(code.getKey()).normalize();
                if(!(path.startsWith(data.settings.root().resolve("app"))||path.startsWith(data.settings.root().resolve("validation")))||!ReleaseService.sha(path).equals(code.getValue().asText()))return result;files++;
            }
            if(files<5)return result;
            return result.put("available",true).put("epoch",meta.path("epoch").asInt()).put("completedEpochs",meta.path("completedEpochs").asInt()).put("processed",meta.path("cursor").asInt()).put("metadataSha256",ReleaseService.sha(file));
        }catch(Exception unavailable){return result;}
    }
}
