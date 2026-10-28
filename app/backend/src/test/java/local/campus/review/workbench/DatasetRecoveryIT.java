package local.campus.review.workbench;

import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.boot.test.mock.mockito.SpyBean;
import org.springframework.mock.web.MockMultipartFile;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}","campus.workbench.enabled=false"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class DatasetRecoveryIT extends HttpTestSupport {
    @SpyBean DatasetService service;
    @Autowired WorkbenchWorker worker;
    private com.fasterxml.jackson.databind.JsonNode upload(org.springframework.mock.web.MockHttpSession user)throws Exception{
        var file=new MockMultipartFile("file","recover.csv","text/csv","text\n恢复测试正文\n".getBytes(StandardCharsets.UTF_8));
        var response=http.perform(csrf(multipart("/api/workbench/datasets").file(file).param("name","恢复夹具").param("kind","NEWS").param("organizationId","1"),user)).andExpect(status().isOk()).andReturn();
        return json.readTree(response.getResponse().getContentAsString()).path("data");
    }
    @Test void claimAndInitialEventRollbackTogetherOnTransientDatabaseFailure()throws Exception{
        var staff=login("reviewer");var uploaded=upload(staff);String run=uploaded.path("runId").asText();
        var once=new AtomicBoolean(true);
        doAnswer(invocation->{
            Object payload=invocation.getArgument(1);
            if(payload instanceof Map<?,?> map && "RUNNING".equals(map.get("stage")) && once.getAndSet(false))throw new org.springframework.dao.TransientDataAccessResourceException("simulated event connection failure");
            return invocation.callRealMethod();
        }).when(service).event(eq(run),any());
        try{
            boolean injected=false;
            for(int i=0;i<40 && once.get();i++){
                try{worker.runOne();}catch(org.springframework.dao.TransientDataAccessResourceException expected){injected=true;}
            }
            assertTrue(injected,"必须实际到达该任务的初始事件故障点");
            http.perform(get("/api/workbench/runs/"+run).session(staff)).andExpect(jsonPath("$.data.status").value("QUEUED"));
            worker.runOne();
            http.perform(get("/api/workbench/runs/"+run).session(staff)).andExpect(jsonPath("$.data.status").value("COMPLETED"));
        }finally{reset(service);}
    }
    @Test void archiveCannotRacePastAQueuedRunInsert()throws Exception{
        var staff=login("reviewer");var uploaded=upload(staff);String dataset=uploaded.path("datasetId").asText();
        http.perform(csrf(post("/api/workbench/runs/"+uploaded.path("runId").asText()+"/cancel"),staff)).andExpect(status().isOk());
        var paused=new CountDownLatch(1);var release=new CountDownLatch(1);
        doAnswer(invocation->{paused.countDown();assertTrue(release.await(8,TimeUnit.SECONDS));return invocation.callRealMethod();})
            .when(service).insertRun(anyString(),eq(dataset),anyString(),isNull(),eq("AUDIT"),anyString(),anyString(),anyString());
        var startRequest=csrf(post("/api/workbench/datasets/"+dataset+"/runs"),staff).contentType("application/json").content(json.writeValueAsBytes(Map.of("versionId",uploaded.path("versionId").asText(),"action","AUDIT")));
        var archiveRequest=csrf(patch("/api/workbench/datasets/"+dataset),staff).contentType("application/json").content("{\"archived\":true}");
        try(var threads=Executors.newFixedThreadPool(2)){
            var start=threads.submit(()->http.perform(startRequest).andReturn());assertTrue(paused.await(5,TimeUnit.SECONDS));
            var archive=threads.submit(()->http.perform(archiveRequest).andReturn());
            try{archive.get(1500,TimeUnit.MILLISECONDS);}catch(TimeoutException expected){/* row lock serializes the requests */}
            finally{release.countDown();}
            assertEquals(200,start.get(5,TimeUnit.SECONDS).getResponse().getStatus());
            assertEquals(409,archive.get(5,TimeUnit.SECONDS).getResponse().getStatus());
        }finally{release.countDown();reset(service);}
    }
}
