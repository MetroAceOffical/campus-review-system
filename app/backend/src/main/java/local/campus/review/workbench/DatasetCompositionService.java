package local.campus.review.workbench;

import com.fasterxml.jackson.databind.JsonNode;
import local.campus.review.auth.CurrentUser;
import local.campus.review.common.ApiException;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

@Service
public class DatasetCompositionService {
    private final DatasetService data;
    public DatasetCompositionService(DatasetService data){this.data=data;}
    public record Source(String datasetId,String versionId){}
    public record Create(String organizationId,String name,List<Source> sources){}
    static void validateSources(List<Source> sources){
        if(sources==null||sources.size()<2||sources.size()>10)throw new ApiException(400,"VALIDATION_ERROR","请选择2—10个不同数据集的清洗版本");
        var seen=new HashSet<String>();for(var source:sources){if(source==null)throw new ApiException(400,"VALIDATION_ERROR","来源版本无效");DatasetService.identity(source.datasetId());DatasetService.identity(source.versionId());if(!seen.add(source.datasetId()))throw new ApiException(400,"VALIDATION_ERROR","同一数据集只能选择一个版本");}
    }
    public JsonNode create(CurrentUser user,Create request)throws Exception{
        data.role(user);if(request==null)throw new ApiException(400,"VALIDATION_ERROR","请填写组合来源");
        validateSources(request.sources());data.organization(user,request.organizationId());String name=DatasetService.name(request.name());
        var descriptor=data.json.createObjectNode().put("schemaVersion",1);var sources=descriptor.putArray("sources");String kind=null;long rows=0;
        for(var source:request.sources()){
            var dataset=data.dataset(user,source.datasetId());var version=data.version(source.datasetId(),source.versionId());
            if(Boolean.TRUE.equals(dataset.get("archived"))||!"CLEAN".equals(version.get("stage"))||!"READY".equals(version.get("status")))throw new ApiException(409,"VERSION_NOT_READY","请选择未归档数据集已完成的清洗版本");
            String current=dataset.get("kind").toString();if(kind!=null&&!kind.equals(current))throw new ApiException(400,"VALIDATION_ERROR","原始新闻与标签句对不能混合组合");kind=current;
            rows+=((Number)version.get("row_count")).longValue();
            sources.addObject().put("datasetId",source.datasetId()).put("versionId",source.versionId()).put("name",dataset.get("name").toString()).put("sha256",version.get("sha256").toString());
        }
        if(rows>100000)throw new ApiException(400,"VALIDATION_ERROR","组合后最多100000行，请分批组合");
        descriptor.put("kind",kind);String datasetId=DatasetService.uuid(),inputId=DatasetService.uuid(),outputId=DatasetService.uuid(),run=DatasetService.uuid(),type=kind;
        Path folder=data.directory(datasetId,inputId);Files.createDirectories(folder);Path file=folder.resolve("sources.json");Files.writeString(file,descriptor.toString(),StandardOpenOption.CREATE_NEW);
        String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));long inputRows=rows;
        try{data.transactions.executeWithoutResult(tx->{
            // Use deterministic source locks, leaving every input version intact.
            for(var source:request.sources().stream().sorted(Comparator.comparing(Source::datasetId)).toList()){
                if(Boolean.TRUE.equals(data.db.queryForObject("SELECT archived FROM ml_dataset WHERE id=? FOR UPDATE",Boolean.class,source.datasetId())))throw new ApiException(409,"DATASET_ARCHIVED","来源数据集已归档，请刷新后重试");
                var locked=data.db.queryForMap("SELECT sha256,status FROM ml_dataset_version WHERE id=? AND dataset_id=? FOR UPDATE",source.versionId(),source.datasetId());
                String expected="";for(var item:sources)if(item.path("versionId").asText().equals(source.versionId()))expected=item.path("sha256").asText();
                if(!"READY".equals(locked.get("status"))||!expected.equals(locked.get("sha256")))throw new ApiException(409,"VERSION_CHANGED","来源版本已变化，请重新选择");
            }
            data.db.update("INSERT INTO ml_dataset(id,organization_id,name,kind,created_by,created_at,updated_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",datasetId,request.organizationId(),name,type,user.userId());
            data.db.update("INSERT INTO ml_dataset_version(id,dataset_id,stage,status,file_name,sha256,row_count,mapping_json,created_at) VALUES(?,?,'RAW','READY','sources.json',?,?,'{}',UTC_TIMESTAMP(3))",inputId,datasetId,sha,inputRows);
            data.db.update("INSERT INTO ml_dataset_version(id,dataset_id,parent_version_id,stage,status,file_name,mapping_json,created_at) VALUES(?,?,?,'CLEAN','PROCESSING','corpus.jsonl','{}',UTC_TIMESTAMP(3))",outputId,datasetId,inputId);
            data.insertRun(run,datasetId,inputId,outputId,"COMPOSE","{}","{}",user.userId());
        });}catch(Exception error){Files.deleteIfExists(file);throw error;}
        return data.json.createObjectNode().put("datasetId",datasetId).put("versionId",outputId).put("runId",run);
    }
}
