package local.campus.review.detection;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
class QueueIT {
    @Autowired JdbcTemplate db;
    @Autowired ObjectMapper json;
    @Autowired DetectionService detection;
    @Autowired JobWorker jobs;
    @Test void thirteenItemsAndOnlyOneClaim() throws Exception {
        var content=json.createObjectNode().put("type","doc");var nodes=content.putArray("content");
        for(int i=0;i<6;i++)nodes.addObject().put("type","campusImage").putObject("attrs").put("nodeId","image-"+i).put("fileId","1");
        String version=DetectionFixtures.version(db,json.writeValueAsString(content));
        String batch=detection.createFormalBatch(version,"a".repeat(64));
        assertEquals(13,db.queryForObject("SELECT COUNT(*) FROM detection_item WHERE batch_id=?",Integer.class,batch));
        String job=db.queryForObject("SELECT id FROM background_job WHERE batch_id=?",String.class,batch);
        try(var executor=Executors.newFixedThreadPool(2)){
            var gate=new CountDownLatch(1);var futures=new ArrayList<Future<Boolean>>();
            for(int i=0;i<2;i++)futures.add(executor.submit(()->{gate.await();return jobs.claim(job,UUID.randomUUID().toString());}));
            gate.countDown();int count=0;for(var future:futures)if(future.get())count++;
            assertEquals(1,count);
        }
    }
}
