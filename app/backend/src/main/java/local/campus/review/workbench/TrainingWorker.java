package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.annotation.PreDestroy;
import local.campus.review.common.JsonSupport;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** One persistent compute queue, independent of the online review queue. */
@Component
public class TrainingWorker {
    final TrainingService training;final DatasetService data;private final boolean enabled;
    private volatile boolean ready;private final AtomicBoolean busy=new AtomicBoolean();
    private final ExecutorService executor=Executors.newSingleThreadExecutor(r->{var t=new Thread(r,"training-worker");t.setDaemon(true);return t;});
    private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"training-monitor");t.setDaemon(true);return t;});
    private volatile long retryAfter;
    public TrainingWorker(TrainingService training,@Value("${campus.workbench.enabled:true}")boolean enabled){this.training=training;this.data=training.data;this.enabled=enabled;}
    @EventListener(ApplicationReadyEvent.class) public void ready(){ready=true;}
    @Scheduled(fixedDelay=1000) public void poll(){
        if(!ready || !enabled || System.currentTimeMillis()<retryAfter || !busy.compareAndSet(false,true))return;
        executor.submit(()->{try{runOne();}catch(Exception error){org.slf4j.LoggerFactory.getLogger(getClass()).warn("Training worker unavailable ({})",error.getClass().getSimpleName());}finally{busy.set(false);}});
    }
    private void terminate(Process process){process.descendants().forEach(ProcessHandle::destroyForcibly);process.destroyForcibly();}
    public synchronized void runOne()throws Exception{
        try(var connection=data.db.getDataSource().getConnection();var claim=connection.prepareStatement("SELECT GET_LOCK(?,0)")){
            String lock=connection.getCatalog()+":training-worker";claim.setString(1,lock);
            try(var result=claim.executeQuery()){if(!result.next() || result.getInt(1)!=1)return;}
            try{
                data.transactions.executeWithoutResult(tx->{
                    for(var row:data.db.queryForList("SELECT id FROM ml_run WHERE status='RUNNING' AND action IN ('PREPARE','GENERATE','TRAIN','EVALUATE','PREDICT')")){
                        data.db.update("UPDATE ml_run SET status='INTERRUPTED',finished_at=UTC_TIMESTAMP(3),error_message='服务已重启，请复制参数重新运行' WHERE id=? AND status='RUNNING'",row.get("id"));
                        data.event(row.get("id").toString(),Map.of("stage","INTERRUPTED"));
                    }
                });
                var jobs=data.db.queryForList("SELECT * FROM ml_run WHERE status='QUEUED' AND action IN ('PREPARE','GENERATE','TRAIN','EVALUATE','PREDICT') ORDER BY created_at,id LIMIT 1");
                if(jobs.isEmpty())return;var job=jobs.getFirst();String id=job.get("id").toString();
                Boolean claimed=data.transactions.execute(tx->{if(data.db.update("UPDATE ml_run SET status='RUNNING',started_at=COALESCE(started_at,UTC_TIMESTAMP(3)) WHERE id=? AND status='QUEUED'",id)!=1)return false;data.event(id,Map.of("stage","RESOURCE_CHECK"));return true;});
                if(!Boolean.TRUE.equals(claimed))return;
                try{execute(job);}catch(Exception error){
                    String text=Objects.toString(error.getMessage(),"模型任务失败");if(text.length()>900)text=text.substring(0,900);String message=text;
                    data.transactions.executeWithoutResult(tx->{if(data.db.update("UPDATE ml_run SET status='FAILED',error_message=?,finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status='RUNNING'",message,id)==1)data.event(id,Map.of("stage","FAILED","message",message));});
                }
            }finally{try(var release=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){release.setString(1,lock);release.execute();}}
        }
    }
    private void execute(Map<String,Object> job)throws Exception{
        String id=job.get("id").toString(),action=job.get("action").toString(),dataset=job.get("dataset_id").toString();
        if(TrainingService.TRAINING_ACTIONS.contains(action)&&data.db.queryForObject("SELECT COUNT(*) FROM app_user WHERE id=? AND role='ADMIN' AND enabled=true",Integer.class,job.get("created_by"))!=1)throw new IOException("训练任务仅限启用的管理员执行");
        var options=JsonSupport.parse(data.json,job.get("options_json").toString());var source=data.version(dataset,job.get("input_version_id").toString());
        boolean uploaded=action.equals("PREDICT")&&"UPLOADED_FILE".equals(options.path("inputKind").asText());
        Path input=uploaded?null:data.input(source);if(input!=null&&!sha(input).equals(source.get("sha256")))throw new IOException("清洗数据校验失败");
        Path directory=training.directory(id);Files.createDirectories(directory);Path output=directory.resolve("output");
        var config=data.json.createObjectNode().put("action",action).put("output",output.toString()).put("runtime",data.settings.runtime().toString());
        if(uploaded){
            var descriptor=options.path("predictionInput");String format=descriptor.path("format").asText();
            if(!Set.of("csv","jsonl").contains(format))throw new IOException("预测文件格式无效");
            Path upload=directory.resolve("prediction-source."+format);
            if(!Files.isRegularFile(upload)||!upload.toRealPath().startsWith(directory.toRealPath())||!sha(upload).equals(descriptor.path("sha256").asText()))throw new IOException("预测文件校验失败");
            config.set("predictionInput",descriptor.deepCopy());((ObjectNode)config.path("predictionInput")).put("path",upload.toString());
        }else config.put("input",input.toString());
        config.put("kind",data.db.queryForObject("SELECT kind FROM ml_dataset WHERE id=?",String.class,dataset));
        config.set("parameters",options.path("parameters"));
        if(options.has("family"))config.put("family",options.path("family").asText());
        if(options.has("preparationId"))config.put("preparation",training.directory(options.path("preparationId").asText()).resolve("output").toString());
        if(options.has("resumeRunId"))config.put("resume",training.directory(options.path("resumeRunId").asText()).toString());
        if(action.equals("TRAIN")&&options.has("resumeRunId"))config.set("resumeTraining",data.json.createObjectNode().put("folder",training.directory(options.path("resumeRunId").asText()).resolve("output").toString()).put("metadataSha256",options.path("resumeMetadataSha256").asText()));
        if(action.equals("GENERATE")){
            var caches=config.putArray("caches");
            for(var previous:data.db.queryForList("SELECT id FROM ml_run WHERE dataset_id=? AND input_version_id=? AND action='GENERATE' AND id<>? AND status IN ('COMPLETED','CANCELLED','INTERRUPTED','FAILED') ORDER BY created_at DESC LIMIT 20",dataset,source.get("id"),id)){
                var folder=training.directory(previous.get("id").toString());if(Files.isRegularFile(folder.resolve("generation.sqlite")))caches.add(folder.toString());
            }
        }
        if(options.has("modelId")){
            String modelRun=data.db.queryForObject("SELECT run_id FROM ml_model WHERE id=?",String.class,options.path("modelId").asText());
            var model=data.db.queryForMap("SELECT manifest_json FROM ml_model WHERE id=?",options.path("modelId").asText());
            config.put("model",training.directory(modelRun).resolve("output").toString());
            config.put("device",JsonSupport.parse(data.json,model.get("manifest_json").toString()).path("parameters").path("device").asText("cpu"));
        }else config.put("device",options.path("parameters").path("device").asText(action.equals("GENERATE")?"cuda":"cpu"));
        if(options.has("rows"))config.set("rows",options.get("rows"));
        Path configFile=directory.resolve("config.json");Files.writeString(configFile,config.toString());
        Path python=data.settings.root().resolve("runtime/environments/final-training/Scripts/python.exe");
        if(!Files.isRegularFile(python))throw new IOException("项目隔离训练环境尚未就绪");
        var builder=new ProcessBuilder(python.toString(),"-B",data.settings.root().resolve("app/scripts/workbench_training.py").toString(),"--config-file",configFile.toString()).directory(data.settings.root().toFile()).redirectError(directory.resolve("stderr.log").toFile());
        builder.environment().put("HF_HUB_OFFLINE","1");builder.environment().put("TOKENIZERS_PARALLELISM","false");builder.environment().put("OMP_NUM_THREADS","4");builder.environment().put("PYTHONIOENCODING","utf-8");
        var process=builder.start();data.processes.put(id,process);JsonNode result=null;String message="模型任务未完成";
        var monitor=timer.scheduleWithFixedDelay(()->{try{if(!"RUNNING".equals(data.db.queryForObject("SELECT status FROM ml_run WHERE id=?",String.class,id)))terminate(process);else data.event(id,Map.of("stage","HEARTBEAT","elapsedSeconds",process.info().startInstant().map(start->java.time.Duration.between(start,java.time.Instant.now()).toSeconds()).orElse(0L)));}catch(Exception error){terminate(process);}},5,5,TimeUnit.SECONDS);
        int code;
        try(var reader=new BufferedReader(new InputStreamReader(process.getInputStream(),StandardCharsets.UTF_8));var log=Files.newBufferedWriter(directory.resolve("events.jsonl"),StandardOpenOption.CREATE,StandardOpenOption.APPEND)){
            if(!"RUNNING".equals(data.db.queryForObject("SELECT status FROM ml_run WHERE id=?",String.class,id)))terminate(process);
            String line;while((line=reader.readLine())!=null){
                log.write(line);log.newLine();log.flush();var value=data.json.readTree(line);
                switch(value.path("type").asText()){
                    case "event" -> data.event(id,value.path("data"));
                    case "result" -> result=value.path("data");
                    case "error" -> message=value.path("data").path("message").asText("模型任务失败");
                    default -> throw new IOException("模型任务返回格式无效");
                }
            }code=process.waitFor();
        }finally{monitor.cancel(false);data.processes.remove(id,process);if(process.isAlive())terminate(process);}
        if(code==75){
            if(data.db.update("UPDATE ml_run SET status='QUEUED' WHERE id=? AND status='RUNNING'",id)==1)data.event(id,Map.of("stage","WAITING_RESOURCE","message",message));
            retryAfter=System.currentTimeMillis()+15000;return;
        }
        if(code!=0 || result==null)throw new IOException(message);
        if(!data.json.readTree(Files.readString(output.resolve("manifest.json"))).equals(result) || !"COMPLETED".equals(result.path("status").asText()))throw new IOException("任务产物未完整保存");
        var artifacts=result.path("artifacts").fields();while(artifacts.hasNext()){
            var artifact=artifacts.next();Path path=output.resolve(artifact.getKey()).normalize();if(!path.startsWith(output) || !sha(path).equals(artifact.getValue().asText()))throw new IOException("任务产物校验失败");
        }
        JsonNode completed=result;
        data.transactions.executeWithoutResult(tx->{
            if(!"RUNNING".equals(data.db.queryForObject("SELECT status FROM ml_run WHERE id=? FOR UPDATE",String.class,id)))return;
            if(action.equals("TRAIN")){
                String org=data.db.queryForObject("SELECT organization_id FROM ml_dataset WHERE id=?",String.class,dataset);
                data.db.update("INSERT INTO ml_model(id,organization_id,dataset_id,run_id,name,family,manifest_json,created_at) VALUES(?,?,?,?,?,?,?,UTC_TIMESTAMP(3))",id,org,dataset,id,options.path("name").asText(),options.path("family").asText(),completed.toString());
            }
            data.db.update("UPDATE ml_run SET status='COMPLETED',result_json=?,finished_at=UTC_TIMESTAMP(3) WHERE id=?",completed.toString(),id);data.event(id,Map.of("stage","COMPLETED","action",action));
        });
    }
    private String sha(Path file)throws Exception{var digest=java.security.MessageDigest.getInstance("SHA-256");try(var stream=Files.newInputStream(file)){byte[] buffer=new byte[65536];int n;while((n=stream.read(buffer))!=-1)digest.update(buffer,0,n);}return HexFormat.of().formatHex(digest.digest());}
    @PreDestroy public void close(){ready=false;data.processes.values().forEach(this::terminate);executor.shutdownNow();timer.shutdownNow();}
}
