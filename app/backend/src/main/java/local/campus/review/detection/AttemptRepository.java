package local.campus.review.detection;

import com.fasterxml.jackson.databind.*;
import local.campus.review.common.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;

@Repository
public class AttemptRepository {
    private final JdbcTemplate db;private final ObjectMapper json;
    public AttemptRepository(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
    @Transactional public String start(String itemId,JsonNode config){
        var item=db.queryForMap("SELECT * FROM detection_item WHERE id=? FOR UPDATE",itemId);
        if(!"QUEUED".equals(item.get("status")))throw new ApiException(409,"INVALID_STATE","检测项不在等待状态");
        int number=db.queryForObject("SELECT COALESCE(MAX(attempt_no),0)+1 FROM detection_attempt WHERE item_id=?",Integer.class,itemId);
        long id=SqlSupport.insert(db,"INSERT INTO detection_attempt(item_id,attempt_no,status,model_config_json,result_json,started_at) VALUES(?,?,'RUNNING',?,'{}',UTC_TIMESTAMP(3))",itemId,number,JsonSupport.encode(json,config));
        db.update("UPDATE detection_item SET active_attempt_id=?,status='RUNNING',updated_at=UTC_TIMESTAMP(3) WHERE id=?",id,itemId);
        return Long.toString(id);
    }
    private Map<String,Object> locked(String attempt){
        var relation=db.queryForMap("SELECT i.batch_id FROM detection_attempt a JOIN detection_item i ON i.id=a.item_id WHERE a.id=?",attempt);
        db.queryForMap("SELECT id FROM detection_batch WHERE id=? FOR UPDATE",relation.get("batch_id"));
        return db.queryForMap("SELECT a.status AS attempt_status,a.item_id,a.result_json,i.active_attempt_id,b.cancelled_at,v.lifecycle_status FROM detection_attempt a JOIN detection_item i ON i.id=a.item_id JOIN detection_batch b ON b.id=i.batch_id JOIN submission_version v ON v.id=b.submission_version_id WHERE a.id=? FOR UPDATE",attempt);
    }
    private boolean current(Map<String,Object> row,String id){return "RUNNING".equals(row.get("attempt_status")) && id.equals(Objects.toString(row.get("active_attempt_id"),""));}
    private boolean cancelled(Map<String,Object> row){return row.get("cancelled_at")!=null || Set.of("WITHDRAWN","SUPERSEDED").contains(row.get("lifecycle_status"));}
    @Transactional public boolean completeIfCurrent(String attempt,JsonNode result){
        var row=locked(attempt);if(!current(row,attempt))return false;
        if(cancelled(row)){end(row,attempt,"CANCELLED",json.createObjectNode(),"BATCH_CANCELLED",null);return false;}
        String status="NOT_APPLICABLE".equals(result.path("status").asText())?"NOT_APPLICABLE":"COMPLETED";
        end(row,attempt,status,result,null,null);return true;
    }
    @Transactional public boolean failIfCurrent(String attempt,String code,String message){
        var row=locked(attempt);if(!current(row,attempt))return false;
        var retained=(com.fasterxml.jackson.databind.node.ObjectNode)JsonSupport.parse(json,row.get("result_json").toString());
        if(retained.has("ocrStatus") && !"COMPLETED".equals(retained.path("textSearchStatus").asText()))retained.put("textSearchStatus","FAILED").put("textSearchErrorCode",code);
        end(row,attempt,cancelled(row)?"CANCELLED":"FAILED",retained,code,message);return true;
    }
    @Transactional public boolean checkpointIfCurrent(String attempt,JsonNode result){
        var row=locked(attempt);if(!current(row,attempt) || cancelled(row))return false;
        return db.update("UPDATE detection_attempt SET result_json=? WHERE id=? AND status='RUNNING'",JsonSupport.encode(json,result),attempt)==1;
    }
    private void end(Map<String,Object> row,String attempt,String status,JsonNode result,String code,String message){
        db.update("UPDATE detection_attempt SET status=?,result_json=?,error_code=?,error_message=?,finished_at=UTC_TIMESTAMP(3) WHERE id=? AND status='RUNNING'",status,JsonSupport.encode(json,result),code,message,attempt);
        db.update("UPDATE detection_item SET status=?,updated_at=UTC_TIMESTAMP(3) WHERE id=? AND active_attempt_id=?",status,row.get("item_id"),attempt);
    }
}
