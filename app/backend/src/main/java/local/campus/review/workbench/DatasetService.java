package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

@Service
public class DatasetService {
    static final long UPLOAD_LIMIT=50L*1024*1024;
    static final Set<String> TERMINAL=Set.of("COMPLETED","FAILED","CANCELLED","INTERRUPTED");
    final JdbcTemplate db;
    final RuntimeSettings settings;
    final ObjectMapper json;
    final TransactionTemplate transactions;
    final Map<String,Process> processes=new ConcurrentHashMap<>();

    public DatasetService(JdbcTemplate db,RuntimeSettings settings,ObjectMapper json,PlatformTransactionManager manager){
        this.db=db;this.settings=settings;this.json=json;this.transactions=new TransactionTemplate(manager);
    }
    static String uuid(){return UUID.randomUUID().toString();}
    static void identity(String id){if(id==null || !id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"))throw missing();}
    static ApiException missing(){return new ApiException(404,"RESOURCE_NOT_FOUND","未找到可访问的数据");}
    void role(CurrentUser user){if(user.role()!=CurrentUser.Role.ADMIN && user.role()!=CurrentUser.Role.REVIEWER)throw new ApiException(403,"ACCESS_DENIED","仅审核员和管理员可管理数据集与模型");}
    void organization(CurrentUser user,String id){
        role(user);
        if(id==null || !id.matches("[1-9][0-9]{0,18}"))throw missing();
        if(db.queryForObject("SELECT COUNT(*) FROM organization WHERE id=? AND enabled=true",Integer.class,id)!=1)throw missing();
    }
    public JsonNode organizations(CurrentUser user){
        role(user);var result=json.createArrayNode();
        var query=db.queryForList("SELECT id,name FROM organization WHERE enabled=true ORDER BY id");
        for(var row:query)result.addObject().put("organizationId",row.get("id").toString()).put("name",row.get("name").toString());
        return result;
    }
    Map<String,Object> dataset(CurrentUser user,String id){
        role(user);identity(id);var rows=db.queryForList("SELECT * FROM ml_dataset WHERE id=?",id);
        if(rows.isEmpty())throw missing();var row=rows.getFirst();organization(user,row.get("organization_id").toString());return row;
    }
    Map<String,Object> version(String dataset,String id){
        identity(id);var rows=db.queryForList("SELECT * FROM ml_dataset_version WHERE id=? AND dataset_id=?",id,dataset);
        if(rows.isEmpty())throw missing();return rows.getFirst();
    }
    Path directory(String dataset,String version){identity(dataset);identity(version);return settings.runtime().resolve("workbench/datasets").resolve(dataset).resolve(version);}
    Path input(Map<String,Object> version){return directory(version.get("dataset_id").toString(),version.get("id").toString()).resolve("RAW".equals(version.get("stage"))?version.get("file_name").toString():"corpus.jsonl");}
    static String name(String value){if(value==null || value.isBlank() || value.length()>120)throw new ApiException(400,"VALIDATION_ERROR","数据集名称须为1—120字");return value.strip();}
    public JsonNode upload(CurrentUser user,String organization,String name,String kind,MultipartFile file)throws Exception{
        organization(user,organization);String label=name(name);
        if(!Set.of("NEWS","PAIRS").contains(kind))throw new ApiException(400,"VALIDATION_ERROR","请选择原始新闻或标签句对");
        if(file.isEmpty())throw new ApiException(400,"VALIDATION_ERROR","请选择数据文件");
        if(file.getSize()>UPLOAD_LIMIT)throw new ApiException(413,"UPLOAD_TOO_LARGE","数据文件不能超过50MiB");
        String filename=Objects.toString(file.getOriginalFilename(),"").toLowerCase(Locale.ROOT);
        String extension=filename.endsWith(".jsonl")?".jsonl":filename.endsWith(".csv")?".csv":null;
        if(extension==null)throw new ApiException(415,"UNSUPPORTED_DATASET","请上传CSV或JSONL文件");
        String dataset=uuid(),version=uuid(),run=uuid(),stored="source"+extension;
        Path dir=directory(dataset,version);Files.createDirectories(dir);
        var digest=MessageDigest.getInstance("SHA-256");long bytes=0;
        try(var in=file.getInputStream();var out=Files.newOutputStream(dir.resolve(stored),StandardOpenOption.CREATE_NEW)){
            byte[] buffer=new byte[65536];int count;
            while((count=in.read(buffer))!=-1){bytes+=count;if(bytes>UPLOAD_LIMIT)throw new ApiException(413,"UPLOAD_TOO_LARGE","数据文件不能超过50MiB");digest.update(buffer,0,count);out.write(buffer,0,count);}
        }catch(Exception error){Files.deleteIfExists(dir.resolve(stored));throw error;}
        String sha=HexFormat.of().formatHex(digest.digest());
        transactions.executeWithoutResult(tx->{
            db.update("INSERT INTO ml_dataset(id,organization_id,name,kind,created_by,created_at,updated_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",dataset,organization,label,kind,user.userId());
            db.update("INSERT INTO ml_dataset_version(id,dataset_id,stage,status,file_name,sha256,mapping_json,created_at) VALUES(?,?,'RAW','READY',?,?,'{}',UTC_TIMESTAMP(3))",version,dataset,stored,sha);
            insertRun(run,dataset,version,null,"AUDIT","{}","{}",user.userId());
        });
        return json.createObjectNode().put("datasetId",dataset).put("versionId",version).put("runId",run).put("sha256",sha);
    }
    void insertRun(String id,String dataset,String input,String output,String action,String mapping,String options,String user){
        db.update("INSERT INTO ml_run(id,dataset_id,input_version_id,output_version_id,action,status,mapping_json,options_json,created_by,created_at) VALUES(?,?,?,?,?,'QUEUED',?,?,?,UTC_TIMESTAMP(3))",id,dataset,input,output,action,mapping,options,user);
        event(id,Map.of("stage","QUEUED"));
    }
    public JsonNode list(CurrentUser user,int page,int size,String q,boolean archived){
        role(user);if(page<1 || size<1 || size>100 || q.length()>120)throw new ApiException(400,"VALIDATION_ERROR","列表参数无效");
        String from=" FROM ml_dataset d JOIN organization o ON o.id=d.organization_id WHERE o.enabled=true AND d.archived=? AND d.name LIKE ?";
        var args=new ArrayList<Object>(List.of(archived,"%"+q+"%"));
        var result=json.createObjectNode().put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray())).put("page",page).put("pageSize",size);
        args.add(size);args.add((long)(page-1)*size);var items=result.putArray("items");
        for(var row:db.queryForList("SELECT d.*,o.name AS organization_name"+from+" ORDER BY d.updated_at DESC,d.id LIMIT ? OFFSET ?",args.toArray()))items.add(summary(row));
        return result;
    }
    JsonNode summary(Map<String,Object> row){return json.createObjectNode().put("datasetId",row.get("id").toString()).put("organizationId",row.get("organization_id").toString()).put("name",row.get("name").toString()).put("kind",row.get("kind").toString()).put("archived",Boolean.TRUE.equals(row.get("archived"))).put("updatedAt",row.get("updated_at").toString());}
    public JsonNode get(CurrentUser user,String id){
        var row=dataset(user,id);var result=(com.fasterxml.jackson.databind.node.ObjectNode)summary(row);
        var versions=result.putArray("versions");for(var version:db.queryForList("SELECT * FROM ml_dataset_version WHERE dataset_id=? ORDER BY created_at DESC,id",id)){
            var item=versions.addObject().put("versionId",version.get("id").toString()).put("stage",version.get("stage").toString()).put("status",version.get("status").toString()).put("sha256",Objects.toString(version.get("sha256"),"")).put("createdAt",version.get("created_at").toString());
            if(version.get("row_count")==null)item.putNull("rowCount");else item.put("rowCount",((Number)version.get("row_count")).longValue());
        }
        var runs=result.putArray("runs");for(var task:db.queryForList("SELECT * FROM ml_run WHERE dataset_id=? ORDER BY created_at DESC,id LIMIT 50",id))runs.add(runJson(task));return result;
    }
    public JsonNode update(CurrentUser user,String id,String name,Boolean archived){
        dataset(user,id);if(name==null && archived==null)throw new ApiException(400,"VALIDATION_ERROR","请填写修改内容");
        String updatedName=name==null?null:name(name);
        transactions.executeWithoutResult(tx->{
            db.queryForObject("SELECT archived FROM ml_dataset WHERE id=? FOR UPDATE",Boolean.class,id);
            if(Boolean.TRUE.equals(archived) && db.queryForObject("SELECT COUNT(*) FROM ml_run WHERE dataset_id=? AND status IN ('QUEUED','RUNNING')",Integer.class,id)>0)throw new ApiException(409,"TASK_ACTIVE","请先结束运行中的任务");
            if(updatedName!=null)db.update("UPDATE ml_dataset SET name=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?",updatedName,id);
            if(archived!=null)db.update("UPDATE ml_dataset SET archived=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?",archived,id);
        });
        return get(user,id);
    }
    public JsonNode start(CurrentUser user,String id,String versionId,String action,JsonNode mapping,JsonNode options){
        var dataset=dataset(user,id);if(Boolean.TRUE.equals(dataset.get("archived")))throw new ApiException(409,"DATASET_ARCHIVED","请先恢复数据集");
        var source=version(id,versionId);if(!"READY".equals(source.get("status")))throw new ApiException(409,"VERSION_NOT_READY","数据版本尚未就绪");
        if(action==null || !Set.of("AUDIT","CLEAN").contains(action))throw new ApiException(400,"VALIDATION_ERROR","请选择质量评估或数据清洗");
        if(mapping==null)mapping=json.createObjectNode();if(options==null)options=json.createObjectNode();
        if(!mapping.isObject() || !options.isObject() || mapping.toString().length()>10000 || options.toString().length()>10000)throw new ApiException(400,"VALIDATION_ERROR","映射或清洗参数无效");
        String run=uuid(),output="CLEAN".equals(action)?uuid():null,mapped=mapping.toString(),settings=options.toString();
        transactions.executeWithoutResult(tx->{
            if(Boolean.TRUE.equals(db.queryForObject("SELECT archived FROM ml_dataset WHERE id=? FOR UPDATE",Boolean.class,id)))throw new ApiException(409,"DATASET_ARCHIVED","请先恢复数据集");
            if(output!=null)db.update("INSERT INTO ml_dataset_version(id,dataset_id,parent_version_id,stage,status,file_name,mapping_json,created_at) VALUES(?,?,?,'CLEAN','PROCESSING','corpus.jsonl',?,UTC_TIMESTAMP(3))",output,id,versionId,mapped);
            insertRun(run,id,versionId,output,action,mapped,settings,user.userId());
        });return json.createObjectNode().put("runId",run);
    }
    Map<String,Object> runRow(CurrentUser user,String id){identity(id);var rows=db.queryForList("SELECT * FROM ml_run WHERE id=?",id);if(rows.isEmpty())throw missing();dataset(user,rows.getFirst().get("dataset_id").toString());return rows.getFirst();}
    JsonNode runJson(Map<String,Object> task){
        var node=json.createObjectNode().put("runId",task.get("id").toString()).put("datasetId",task.get("dataset_id").toString()).put("inputVersionId",task.get("input_version_id").toString()).put("outputVersionId",Objects.toString(task.get("output_version_id"),"")).put("action",task.get("action").toString()).put("status",task.get("status").toString()).put("error",Objects.toString(task.get("error_message"),"")).put("createdAt",task.get("created_at").toString());
        node.set("mapping",JsonSupport.parse(json,task.get("mapping_json").toString()));node.set("options",JsonSupport.parse(json,task.get("options_json").toString()));
        if(task.get("result_json")!=null)node.set("result",JsonSupport.parse(json,task.get("result_json").toString()));
        return node;
    }
    public JsonNode run(CurrentUser user,String id){return runJson(runRow(user,id));}
    void event(String run,Object payload){db.update("INSERT INTO ml_run_event(run_id,payload_json,created_at) VALUES(?,?,UTC_TIMESTAMP(3))",run,JsonSupport.encode(json,payload));}
    public JsonNode events(CurrentUser user,String id,long after){runRow(user,id);if(after<0)throw new ApiException(400,"VALIDATION_ERROR","事件序号无效");return storedEvents(id,after);}
    JsonNode storedEvents(String id,long after){var result=json.createArrayNode();for(var row:db.queryForList("SELECT id,payload_json FROM ml_run_event WHERE run_id=? AND id>? ORDER BY id LIMIT 500",id,after))result.addObject().put("sequence",((Number)row.get("id")).longValue()).set("data",JsonSupport.parse(json,row.get("payload_json").toString()));return result;}
    public JsonNode cancel(CurrentUser user,String id){
        runRow(user,id);transactions.executeWithoutResult(tx->{
            if(db.update("UPDATE ml_run SET status='CANCELLED',finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status IN ('QUEUED','RUNNING')",id)==1){
                db.update("UPDATE ml_dataset_version v JOIN ml_run r ON r.output_version_id=v.id SET v.status='CANCELLED' WHERE r.id=?",id);event(id,Map.of("stage","CANCELLED"));
            }
        });var process=processes.get(id);if(process!=null)stopProcess(process);return run(user,id);
    }
    static void stopProcess(Process process){process.descendants().forEach(ProcessHandle::destroyForcibly);process.destroyForcibly();}
    public Path download(CurrentUser user,String id,String versionId,String artifact){
        dataset(user,id);var version=version(id,versionId);
        Set<String> allowed=Set.of("corpus.jsonl","manifest.json","audit.json","cleaning.json","quarantine.jsonl","changes.jsonl","events.jsonl");
        Path file;
        if("source".equals(artifact) && "RAW".equals(version.get("stage")))file=input(version);
        else {if(!"READY".equals(version.get("status")) || !"CLEAN".equals(version.get("stage")) || !allowed.contains(artifact))throw missing();file=directory(id,versionId).resolve(artifact);}
        if(!Files.isRegularFile(file))throw missing();return file;
    }
    public JsonNode rows(CurrentUser user,String id,String versionId,int page,int size)throws Exception{
        if(page<1 || size<1 || size>100)throw new ApiException(400,"VALIDATION_ERROR","分页参数无效");
        Path file=download(user,id,versionId,"corpus.jsonl");var source=version(id,versionId);
        var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",((Number)source.get("row_count")).longValue());var items=result.putArray("items");
        try(var stream=Files.lines(file)){for(var line:stream.skip((long)(page-1)*size).limit(size).toList()){
            var row=json.readTree(line);var preview=json.createObjectNode();row.fields().forEachRemaining(entry->{if(!entry.getKey().equals("_provenance"))preview.set(entry.getKey(),entry.getValue().isTextual() && entry.getValue().asText().length()>1000?json.getNodeFactory().textNode(entry.getValue().asText().substring(0,1000)):entry.getValue());});items.add(preview);
        }}return result;
    }
}
