package local.campus.review.detection;

import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import javax.sql.DataSource;
import java.util.*;

@Service
public class RecoveryService {
    private final JdbcTemplate db;private final DataSource source;private final TransactionTemplate tx;private final ProcessSupervisor supervisor;
    public RecoveryService(JdbcTemplate db,DataSource source,TransactionTemplate tx,ProcessSupervisor supervisor){this.db=db;this.source=source;this.tx=tx;this.supervisor=supervisor;}
    public boolean recoverPreviousRun(String owner){
        try(var connection=source.getConnection();var lock=connection.prepareStatement("SELECT GET_LOCK(?,0)")){
            String name=connection.getCatalog()+":worker";lock.setString(1,name);try(var result=lock.executeQuery()){if(!result.next()||result.getInt(1)!=1)return false;}
            try{
                if(db.queryForObject("SELECT COUNT(*) FROM background_job WHERE status='RUNNING' AND (owner_run_id IS NULL OR owner_run_id<>?)",Integer.class,owner)==0)return true;
                // Unreachable is not idle. A restarted service can prove readiness with its new runId.
                if(!supervisor.ensureReady(false)||!supervisor.ensureReady(true))return false;
                tx.executeWithoutResult(status->{
                    var jobs=db.queryForList("SELECT * FROM background_job WHERE status='RUNNING' AND (owner_run_id IS NULL OR owner_run_id<>?) ORDER BY id FOR UPDATE",owner);
                    for(var job:jobs){
                        Object batch=job.get("batch_id");if(batch==null&&job.get("item_id")!=null)batch=db.queryForObject("SELECT batch_id FROM detection_item WHERE id=?",String.class,job.get("item_id"));
                        boolean cancelled=false;
                        if(batch!=null){
                            var row=db.queryForMap("SELECT b.cancelled_at,v.lifecycle_status FROM detection_batch b JOIN submission_version v ON v.id=b.submission_version_id WHERE b.id=? FOR UPDATE",batch);
                            cancelled=row.get("cancelled_at")!=null||Set.of("WITHDRAWN","SUPERSEDED").contains(row.get("lifecycle_status"));
                            String target=cancelled?"CANCELLED":"INTERRUPTED";
                            String filter=job.get("item_id")==null?"i.batch_id=?":"i.id=?";Object value=job.get("item_id")==null?batch:job.get("item_id");
                            db.update("UPDATE detection_attempt a JOIN detection_item i ON i.active_attempt_id=a.id SET a.status=?,a.error_code='PROCESS_INTERRUPTED',a.error_message='上次进程中断，已保留中间结果',a.finished_at=UTC_TIMESTAMP(3) WHERE "+filter+" AND a.status='RUNNING'",target,value);
                            db.update("UPDATE detection_item i SET i.status=?,i.active_attempt_id=IF(?='QUEUED',NULL,i.active_attempt_id),i.updated_at=UTC_TIMESTAMP(3) WHERE "+filter+" AND i.status IN ('RUNNING','QUEUED')",cancelled?"CANCELLED":"QUEUED",cancelled?"CANCELLED":"QUEUED",value);
                            db.update("UPDATE detection_batch SET status=?,finished_at=IF(?='CANCELLED',UTC_TIMESTAMP(3),NULL) WHERE id=?",cancelled?"CANCELLED":"WAITING_SERVICE",cancelled?"CANCELLED":"WAITING_SERVICE",batch);
                        }
                        db.update("UPDATE background_job SET status=?,owner_run_id=NULL,started_at=NULL,finished_at=NULL,error_code='PROCESS_INTERRUPTED' WHERE id=? AND status='RUNNING'",cancelled?"CANCELLED":"WAITING_SERVICE",job.get("id"));
                    }
                });return true;
            }finally{try(var release=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){release.setString(1,name);release.execute();}}
        }catch(Exception failure){throw new IllegalStateException("Queue recovery failed; no automatic reset",failure);}
    }
}
