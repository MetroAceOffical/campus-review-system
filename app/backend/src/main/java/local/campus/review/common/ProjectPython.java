package local.campus.review.common;
import com.fasterxml.jackson.databind.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
public final class ProjectPython {
    private ProjectPython(){}
    public static JsonNode delivery(RuntimeSettings settings,ObjectMapper json,Path folder,JsonNode config)throws Exception{
        Files.createDirectories(folder);Path input=folder.resolve("input.json"),output=folder.resolve("result.json");Files.writeString(input,config.toString());
        var builder=new ProcessBuilder(settings.root().resolve("runtime/environments/final-training/Scripts/python.exe").toString(),"-B",settings.root().resolve("app/scripts/delivery.py").toString(),input.toString()).directory(settings.root().toFile()).redirectOutput(output.toFile()).redirectError(folder.resolve("stderr.log").toFile());
        builder.environment().putAll(Map.of("CUDA_VISIBLE_DEVICES","-1","HF_HUB_OFFLINE","1","OMP_NUM_THREADS","2","MKL_NUM_THREADS","2","PYTHONIOENCODING","utf-8"));var process=builder.start();
        try{if(!process.waitFor(300,TimeUnit.SECONDS))throw new IllegalStateException("交付计算超时，请重试");var result=json.readTree(Files.readString(output));if(process.exitValue()!=0 || result.has("error"))throw new IllegalStateException(result.path("error").asText("交付计算失败"));return result;}finally{if(process.isAlive()){process.descendants().forEach(ProcessHandle::destroyForcibly);process.destroyForcibly();}}
    }
}
