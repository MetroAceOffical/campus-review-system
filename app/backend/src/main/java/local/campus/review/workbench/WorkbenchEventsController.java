package local.campus.review.workbench;

import local.campus.review.auth.CurrentUserService;
import local.campus.review.common.ApiException;
import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import jakarta.annotation.PreDestroy;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

@RestController
@RequestMapping("/api/workbench/runs")
public class WorkbenchEventsController {
    private final DatasetService data;private final CurrentUserService users;
    private final Semaphore slots=new Semaphore(4);
    private final ExecutorService streams=Executors.newFixedThreadPool(4,r->{var t=new Thread(r,"workbench-events");t.setDaemon(true);return t;});
    public WorkbenchEventsController(DatasetService data,CurrentUserService users){this.data=data;this.users=users;}
    @GetMapping(value="/{id}/stream",produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter stream(Authentication auth,@PathVariable String id,@RequestParam(defaultValue="0")long after,@RequestHeader(value="Last-Event-ID",required=false)String resume){
        data.run(users.require(auth),id);
        long previous=after;
        try{if(resume!=null)previous=Math.max(previous,Long.parseLong(resume));}catch(NumberFormatException error){throw new ApiException(400,"VALIDATION_ERROR","事件序号无效");}
        if(previous<0)throw new ApiException(400,"VALIDATION_ERROR","事件序号无效");
        if(!slots.tryAcquire())throw new ApiException(429,"STREAM_LIMIT","实时连接已满，使用自动刷新");
        var emitter=new SseEmitter(35000L);var active=new AtomicBoolean(true);
        emitter.onCompletion(()->active.set(false));emitter.onTimeout(()->active.set(false));emitter.onError(error->active.set(false));
        long cursor=previous;
        streams.submit(()->{
            long last=cursor,deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(30);String lastStatus="";
            try{
                while(active.get() && System.nanoTime()<deadline){
                    var run=data.run(users.require(auth),id);var events=data.storedEvents(id,last);
                    for(var event:events){last=event.path("sequence").asLong();emitter.send(SseEmitter.event().id(Long.toString(last)).name("progress").data(event.path("data")));}
                    String status=run.path("status").asText();
                    if(!status.equals(lastStatus)){emitter.send(SseEmitter.event().name("snapshot").data(java.util.Map.of("status",status,"runId",id)));lastStatus=status;}
                    if(DatasetService.TERMINAL.contains(status) && events.size()<500)break;
                    Thread.sleep(250);
                }
                emitter.complete();
            }catch(Exception error){emitter.completeWithError(error);}finally{slots.release();}
        });return emitter;
    }
    @PreDestroy public void close(){streams.shutdownNow();}
}
