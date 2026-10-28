package local.campus.review.workbench;
import org.springframework.stereotype.Component;
import org.springframework.context.event.EventListener;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.scheduling.annotation.Scheduled;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
@Component
public class DeliveryWorker {
    private final ReleaseService releases;private final ReferenceImportService imports;private final DatasetService data;private volatile boolean ready;
    private final ExecutorService worker=Executors.newSingleThreadExecutor(r->{var t=new Thread(r,"delivery-worker");t.setDaemon(true);return t;});private final AtomicBoolean busy=new AtomicBoolean();
    public DeliveryWorker(ReleaseService releases,ReferenceImportService imports,DatasetService data){this.releases=releases;this.imports=imports;this.data=data;}
    @EventListener(ApplicationReadyEvent.class)public void ready(){data.db.update("UPDATE model_release SET status='INTERRUPTED' WHERE status='VERIFYING'");data.db.update("UPDATE reference_import SET status='INTERRUPTED' WHERE status IN ('RUNNING','INDEXING')");ready=true;}
    @Scheduled(fixedDelay=1000)public void poll(){if(!ready||!busy.compareAndSet(false,true))return;worker.submit(()->{try{run();}catch(Exception e){org.slf4j.LoggerFactory.getLogger(getClass()).warn("Delivery queue unavailable ({})",e.getClass().getSimpleName());}finally{busy.set(false);}});}
    private void run()throws Exception{
        var rows=data.db.queryForList("SELECT * FROM model_release WHERE status='QUEUED' ORDER BY created_at LIMIT 1");if(!rows.isEmpty()){var row=rows.getFirst();String id=row.get("id").toString();data.db.update("UPDATE model_release SET status='VERIFYING' WHERE id=?",id);try{releases.verify(row);}catch(Exception e){data.db.update("UPDATE model_release SET status='FAILED',error_message=? WHERE id=?",message(e),id);}return;}
        try(var connection=data.db.getDataSource().getConnection();var lock=connection.prepareStatement("SELECT GET_LOCK(?,0)")){String name=connection.getCatalog()+":worker";lock.setString(1,name);try(var r=lock.executeQuery()){if(!r.next()||r.getInt(1)!=1)return;}try{var jobs=data.db.queryForList("SELECT * FROM reference_import WHERE status='QUEUED' ORDER BY created_at LIMIT 1");if(jobs.isEmpty())return;var row=jobs.getFirst();String id=row.get("id").toString();data.db.update("UPDATE reference_import SET status='RUNNING' WHERE id=?",id);try{imports.run(row);}catch(Exception e){data.db.update("UPDATE reference_import SET status='FAILED',error_message=? WHERE id=?",message(e),id);}}finally{try(var release=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){release.setString(1,name);release.execute();}}}
    }
    private String message(Exception e){String text=java.util.Objects.toString(e.getMessage(),"交付未完成");return text.substring(0,Math.min(900,text.length()));}
    @PreDestroy public void close(){ready=false;worker.shutdownNow();}
}
