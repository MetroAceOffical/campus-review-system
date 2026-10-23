package local.campus.review.common;

import com.fasterxml.jackson.databind.*;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.util.UUID;

@Component
public class IdempotencyStore {
    private final JdbcTemplate db;private final ObjectMapper json;
    public IdempotencyStore(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
    public JsonNode begin(String actor,String operation,String key,String hash){
        if(!TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Idempotency requires the business transaction");
        try{if(key==null || !UUID.fromString(key).toString().equalsIgnoreCase(key))throw new IllegalArgumentException();}catch(IllegalArgumentException e){throw new ApiException(400,"VALIDATION_ERROR","缺少有效的Idempotency-Key");}
        try{db.update("INSERT INTO idempotency_record(actor_id,operation,request_key,request_sha256,result_json,created_at) VALUES(?,?,?,?,'{}',UTC_TIMESTAMP(3))",actor,operation,key,hash);return null;}
        catch(DuplicateKeyException e){
            var row=db.queryForMap("SELECT request_sha256,result_json FROM idempotency_record WHERE actor_id=? AND operation=? AND request_key=? FOR UPDATE",actor,operation,key);
            if(!hash.equals(row.get("request_sha256")))throw new ApiException(409,"IDEMPOTENCY_CONFLICT","同一请求标识对应的内容已改变，请重新发起");
            var result=JsonSupport.parse(json,row.get("result_json").toString());
            if(result.isEmpty())throw new ApiException(409,"REQUEST_IN_PROGRESS","该请求尚未完成，请稍后重试");return result;
        }
    }
    public void complete(String actor,String operation,String key,JsonNode result){
        if(!TransactionSynchronizationManager.isActualTransactionActive())throw new IllegalStateException("Idempotency requires the business transaction");
        db.update("UPDATE idempotency_record SET result_json=? WHERE actor_id=? AND operation=? AND request_key=?",JsonSupport.encode(json,result),actor,operation,key);
    }
}
