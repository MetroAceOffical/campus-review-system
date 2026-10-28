package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import local.campus.review.common.JsonSupport;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import jakarta.annotation.PreDestroy;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;

/** Serialized CPU data tasks; separate from the detector and GPU training queue. */
@Component
public class WorkbenchWorker {
    private final DatasetService data;
    private final String owner=UUID.randomUUID().toString();
    private final boolean enabled;
    private volatile boolean ready;
    private final java.util.concurrent.atomic.AtomicBoolean busy=new java.util.concurrent.atomic.AtomicBoolean();
    private final ExecutorService executor=Executors.newSingleThreadExecutor(r->{var t=new Thread(r,"dataset-worker");t.setDaemon(true);return t;});
    private static class DatasetFailure extends IOException {
        final JsonNode details;DatasetFailure(String message,JsonNode details){super(message);this.details=details;}
    }
    private final ScheduledExecutorService watchdog=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"dataset-timeout");t.setDaemon(true);return t;});
    public WorkbenchWorker(DatasetService data,@Value("${campus.workbench.enabled:true}")boolean enabled){this.data=data;this.enabled=enabled;}
    @EventListener(ApplicationReadyEvent.class) public void ready(){ready=true;}
    @Scheduled(fixedDelay=500) public void poll(){
        if(!enabled || !ready || !busy.compareAndSet(false,true))return;
        executor.submit(()->{try{runOne();}catch(Exception error){org.slf4j.LoggerFactory.getLogger(getClass()).warn("Dataset worker unavailable ({})",error.getClass().getSimpleName());}finally{busy.set(false);}});
    }
    public synchronized void runOne()throws Exception{
        try(var connection=data.db.getDataSource().getConnection();var statement=connection.prepareStatement("SELECT GET_LOCK(?,0)")){
            String lock=connection.getCatalog()+":dataset-worker";statement.setString(1,lock);
            try(var result=statement.executeQuery()){if(!result.next() || result.getInt(1)!=1)return;}
            try{
                // Acquiring this physical-connection lock proves no data worker
                // is executing a claim here. Recover abandoned claims on every
                // poll, including those left by a transient DB failure.
                data.transactions.executeWithoutResult(tx->{
                        var stale=data.db.queryForList("SELECT id,output_version_id FROM ml_run WHERE status='RUNNING' AND action IN ('AUDIT','CLEAN')");
                        for(var row:stale){
                            data.db.update("UPDATE ml_run SET status='INTERRUPTED',error_message='任务已中断，请重新运行',finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status='RUNNING'",row.get("id"));
                            if(row.get("output_version_id")!=null)data.db.update("UPDATE ml_dataset_version SET status='INTERRUPTED' WHERE id=? AND status='PROCESSING'",row.get("output_version_id"));
                            data.event(row.get("id").toString(),Map.of("stage","INTERRUPTED"));
                        }
                });
                var jobs=data.db.queryForList("SELECT * FROM ml_run WHERE status='QUEUED' AND action IN ('AUDIT','CLEAN') ORDER BY created_at,id LIMIT 1");
                if(jobs.isEmpty())return;var job=jobs.getFirst();String id=job.get("id").toString();
                var claimed=data.transactions.execute(tx->{
                    if(data.db.update("UPDATE ml_run SET status='RUNNING',owner_id=?,started_at=UTC_TIMESTAMP(3) WHERE id=? AND status='QUEUED'",owner,id)!=1)return false;
                    data.event(id,Map.of("stage","RUNNING"));return true;
                });
                if(!Boolean.TRUE.equals(claimed))return;
                try{execute(job);}catch(Exception error){fail(job,error.getMessage()==null?"数据处理未完成":error.getMessage(),error instanceof DatasetFailure failure?failure.details:null);}
            }finally{try(var release=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){release.setString(1,lock);release.execute();}}
        }
    }
    private String sha(Path file)throws Exception{try(var stream=Files.newInputStream(file)){return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(stream.readAllBytes()));}}
    private void execute(Map<String,Object> job)throws Exception{
        String id=job.get("id").toString(),datasetId=job.get("dataset_id").toString(),action=job.get("action").toString();
        var input=data.version(datasetId,job.get("input_version_id").toString());Path file=data.input(input);
        if(!sha(file).equals(input.get("sha256")))throw new IOException("输入文件校验失败，请重新导入");
        String kind=data.db.queryForObject("SELECT kind FROM ml_dataset WHERE id=?",String.class,datasetId);
        var logs=data.settings.runtime().resolve("workbench/logs");Files.createDirectories(logs);
        var config=data.json.createObjectNode();config.set("mapping",JsonSupport.parse(data.json,job.get("mapping_json").toString()));config.set("options",JsonSupport.parse(data.json,job.get("options_json").toString()));
        config.put("internalVersion","CLEAN".equals(input.get("stage")));
        var configFile=logs.resolve(id+".json");Files.writeString(configFile,config.toString(),StandardOpenOption.CREATE_NEW);
        var args=new ArrayList<>(List.of(data.settings.python().toString(),"-B",data.settings.root().resolve("app/scripts/workbench.py").toString(),action.toLowerCase(Locale.ROOT),"--input",file.toString(),"--kind",kind,"--config-file",configFile.toString()));
        Path output=null;
        if("CLEAN".equals(action)){output=data.directory(datasetId,job.get("output_version_id").toString());args.addAll(List.of("--output",output.toString()));}
        var process=new ProcessBuilder(args).directory(data.settings.root().toFile()).redirectError(logs.resolve(id+".log").toFile()).start();
        data.processes.put(id,process);var timeout=watchdog.schedule(process::destroyForcibly,300,TimeUnit.SECONDS);
        JsonNode result=null;String failure=null;JsonNode failureDetails=null;
        try{
            if(!"RUNNING".equals(data.db.queryForObject("SELECT status FROM ml_run WHERE id=?",String.class,id)))process.destroyForcibly();
            try(var reader=new BufferedReader(new InputStreamReader(process.getInputStream(),StandardCharsets.UTF_8))){
                String line;while((line=reader.readLine())!=null){
                    JsonNode value=data.json.readTree(line);if(value==null)continue;
                    switch(value.path("type").asText()){
                        case "event" -> {if("RUNNING".equals(data.db.queryForObject("SELECT status FROM ml_run WHERE id=?",String.class,id)))data.event(id,value.path("data"));}
                        case "result" -> result=value.path("data");
                        case "error" -> {failure=value.path("data").path("message").asText("数据格式错误");failureDetails=value.path("data").path("details");}
                        default -> throw new IOException("数据处理返回格式无效");
                    }
                }
            }
            if(process.waitFor()!=0 || result==null)throw new DatasetFailure(failure==null?"数据任务失败或超时，请查看文件与参数":failure,failureDetails);
        }finally{timeout.cancel(false);data.processes.remove(id,process);if(process.isAlive())process.destroyForcibly();}
        if("CLEAN".equals(action)){
            var manifest=data.json.readTree(Files.readString(output.resolve("manifest.json")));
            if(!manifest.equals(result) || !"COMPLETED".equals(manifest.path("status").asText()) || !manifest.path("inputSha256").asText().equals(input.get("sha256")))throw new IOException("数据版本身份校验失败");
            var fields=manifest.path("artifacts").fields();int artifacts=0;
            while(fields.hasNext()){var artifact=fields.next();if(!Set.of("corpus.jsonl","quarantine.jsonl","changes.jsonl","audit.json","cleaning.json","events.jsonl").contains(artifact.getKey()) || !sha(output.resolve(artifact.getKey())).equals(artifact.getValue().asText()))throw new IOException("数据产物校验失败");artifacts++;}
            if(artifacts!=6)throw new IOException("数据版本产物不完整");
        }else if(!result.path("sourceSha256").asText().equals(input.get("sha256")))throw new IOException("数据质量报告身份不一致");
        JsonNode finalResult=result;
        data.transactions.executeWithoutResult(tx->{
            var state=data.db.queryForObject("SELECT status FROM ml_run WHERE id=? FOR UPDATE",String.class,id);
            if(!"RUNNING".equals(state))return;
            if("CLEAN".equals(action))data.db.update("UPDATE ml_dataset_version SET status='READY',sha256=?,row_count=? WHERE id=?",finalResult.path("artifacts").path("corpus.jsonl").asText(),finalResult.path("outputRows").asLong(),job.get("output_version_id"));
            else data.db.update("UPDATE ml_dataset_version SET row_count=?,mapping_json=? WHERE id=?",finalResult.path("audit").path("totalRows").asLong(),job.get("mapping_json").toString(),input.get("id"));
            data.db.update("UPDATE ml_run SET status='COMPLETED',result_json=?,finished_at=UTC_TIMESTAMP(3) WHERE id=?",finalResult.toString(),id);
            data.db.update("UPDATE ml_dataset SET updated_at=UTC_TIMESTAMP(3) WHERE id=?",datasetId);
            data.event(id,Map.of("stage","COMPLETED","action",action));
        });
    }
    private void fail(Map<String,Object> job,String message,JsonNode details){
        String id=job.get("id").toString();String safe=message.length()>900?message.substring(0,900):message;
        data.transactions.executeWithoutResult(tx->{
            if(data.db.update("UPDATE ml_run SET status='FAILED',error_message=?,result_json=?,finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status='RUNNING'",safe,details==null?null:details.toString(),id)==1){
                if(job.get("output_version_id")!=null)data.db.update("UPDATE ml_dataset_version SET status='FAILED' WHERE id=?",job.get("output_version_id"));
                data.event(id,Map.of("stage","FAILED","message",safe));
            }
        });
    }
    @PreDestroy public void close(){ready=false;data.processes.values().forEach(Process::destroyForcibly);executor.shutdownNow();watchdog.shutdownNow();}
}
