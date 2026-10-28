package local.campus.review.workbench;

import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.mock.web.MockMultipartFile;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.nio.charset.StandardCharsets;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}","campus.workbench.enabled=false"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class DatasetIT extends HttpTestSupport {
    @org.springframework.beans.factory.annotation.Autowired javax.sql.DataSource database;
    @org.springframework.beans.factory.annotation.Autowired WorkbenchWorker worker;
    private com.fasterxml.jackson.databind.JsonNode settled(String run,org.springframework.mock.web.MockHttpSession session)throws Exception{
        com.fasterxml.jackson.databind.JsonNode data=null;
        for(int i=0;i<80;i++){
            worker.runOne();
            var response=http.perform(get("/api/workbench/runs/"+run).session(session)).andExpect(status().isOk()).andReturn();
            data=json.readTree(response.getResponse().getContentAsString()).path("data");
            if(!java.util.Set.of("QUEUED","RUNNING").contains(data.path("status").asText()))break;
            Thread.sleep(200);
        }
        return data;
    }
    private com.fasterxml.jackson.databind.JsonNode finished(String run,org.springframework.mock.web.MockHttpSession session)throws Exception{
        var data=settled(run,session);org.junit.jupiter.api.Assertions.assertEquals("COMPLETED",data.path("status").asText(),data.toString());return data;
    }
    @Test void bulkUploadIsDepartmentScopedAndQueuesRealAudit() throws Exception {
        var member=login("member1"); var other=login("member2"); var reviewer=login("reviewer");
        var file=new MockMultipartFile("file","news.csv","text/csv","编号,正文,来源学校\na,第一篇真实新闻,南京传媒学院\nb,第二篇新闻,其他高校\n".getBytes(StandardCharsets.UTF_8));
        var result=http.perform(csrf(multipart("/api/workbench/datasets").file(file).param("name","数据中心批量夹具").param("kind","NEWS").param("organizationId","1"),member))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.datasetId").isString()).andExpect(jsonPath("$.data.runId").isString()).andReturn();
        var data=json.readTree(result.getResponse().getContentAsString()).path("data"); String id=data.path("datasetId").asText(),run=data.path("runId").asText();
        http.perform(get("/api/workbench/datasets/"+id).session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.name").value("数据中心批量夹具"));
        http.perform(csrf(post("/api/workbench/datasets/"+id+"/runs"),member).contentType("application/json").content(json.writeValueAsBytes(java.util.Map.of("versionId",data.path("versionId").asText())))).andExpect(status().isBadRequest());
        http.perform(get("/api/workbench/datasets/"+id).session(other)).andExpect(status().isNotFound());
        http.perform(get("/api/workbench/runs/"+run).session(other)).andExpect(status().isNotFound());
        http.perform(get("/api/workbench/runs/"+run+"/events").session(other)).andExpect(status().isNotFound());
        http.perform(get("/api/workbench/runs/"+run+"/stream").session(other)).andExpect(status().isNotFound());
        http.perform(csrf(multipart("/api/workbench/datasets").file(file).param("name","越权").param("kind","NEWS").param("organizationId","1"),other)).andExpect(status().isNotFound());
        http.perform(get("/api/workbench/datasets").session(reviewer)).andExpect(status().isForbidden());
        http.perform(get("/api/workbench/datasets?q=数据中心批量夹具").session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(org.hamcrest.Matchers.greaterThanOrEqualTo(1)));
    }

    @Test void realPythonAuditAndCleaningPublishIndependentVersionAndEvents()throws Exception{
        var member=login("member1");var other=login("member2");
        var file=new MockMultipartFile("file","workflow.csv","text/csv","id,title,text\na,一,<p>真实正文</p>\nb,二,真实正文\nc,三,另一篇新闻\nd,空,\n".getBytes(StandardCharsets.UTF_8));
        var response=http.perform(csrf(multipart("/api/workbench/datasets").file(file).param("name","真实清洗链路").param("kind","NEWS").param("organizationId","1"),member)).andExpect(status().isOk()).andReturn();
        var upload=json.readTree(response.getResponse().getContentAsString()).path("data");String dataset=upload.path("datasetId").asText(),raw=upload.path("versionId").asText();
        var audit=finished(upload.path("runId").asText(),member);
        org.junit.jupiter.api.Assertions.assertEquals(4,audit.path("result").path("audit").path("totalRows").asInt());
        var started=http.perform(csrf(post("/api/workbench/datasets/"+dataset+"/runs"),member).contentType("application/json").content(json.writeValueAsBytes(java.util.Map.of("versionId",raw,"action","CLEAN","mapping",java.util.Map.of(),"options",java.util.Map.of())))).andExpect(status().isOk()).andReturn();
        String run=json.readTree(started.getResponse().getContentAsString()).path("data").path("runId").asText();
        var clean=finished(run,member);String output=clean.path("outputVersionId").asText();
        org.junit.jupiter.api.Assertions.assertNotEquals(raw,output);
        org.junit.jupiter.api.Assertions.assertEquals(2,clean.path("result").path("outputRows").asInt());
        org.junit.jupiter.api.Assertions.assertEquals(1,clean.path("result").path("duplicateRows").asInt());
        org.junit.jupiter.api.Assertions.assertEquals(1,clean.path("result").path("quarantineRows").asInt());
        http.perform(get("/api/workbench/datasets/"+dataset+"/versions/"+output+"/rows?pageSize=1").session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.total").value(2)).andExpect(jsonPath("$.data.items.length()").value(1));
        http.perform(get("/api/workbench/datasets/"+dataset+"/versions/"+raw+"/files/source").session(other)).andExpect(status().isNotFound());
        http.perform(get("/api/workbench/datasets/"+dataset+"/versions/"+output+"/files/manifest.json").session(member)).andExpect(status().isOk());
        http.perform(get("/api/workbench/runs/"+run+"/events").session(member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.length()").value(org.hamcrest.Matchers.greaterThan(2)));
        var stream=http.perform(get("/api/workbench/runs/"+run+"/stream").session(member)).andExpect(request().asyncStarted()).andReturn();
        stream.getAsyncResult(5000);
        http.perform(asyncDispatch(stream)).andExpect(status().isOk()).andExpect(content().string(org.hamcrest.Matchers.containsString("event:progress")));
        var again=http.perform(csrf(post("/api/workbench/datasets/"+dataset+"/runs"),member).contentType("application/json").content(json.writeValueAsBytes(java.util.Map.of("versionId",output,"action","CLEAN","mapping",java.util.Map.of(),"options",java.util.Map.of())))).andExpect(status().isOk()).andReturn();
        var reclean=finished(json.readTree(again.getResponse().getContentAsString()).path("data").path("runId").asText(),member);
        var corpus=http.perform(get("/api/workbench/datasets/"+dataset+"/versions/"+reclean.path("outputVersionId").asText()+"/files/corpus.jsonl").session(member)).andExpect(status().isOk()).andReturn();
        var first=json.readTree(corpus.getResponse().getContentAsString(StandardCharsets.UTF_8).split("\n",2)[0]);
        org.junit.jupiter.api.Assertions.assertEquals(2,first.path("_provenance").size(),"再次清洗必须保留已合并来源");
    }
    @Test void unknownColumnCanBeMappedWithoutReuploadingAndQueuedCancelIsDurable()throws Exception{
        var member=login("member1");
        var file=new MockMultipartFile("file","custom.csv","text/csv","新闻内容\n可以恢复处理的新闻正文\n".getBytes(StandardCharsets.UTF_8));
        var response=http.perform(csrf(multipart("/api/workbench/datasets").file(file).param("name","映射恢复").param("kind","NEWS").param("organizationId","1"),member)).andExpect(status().isOk()).andReturn();
        var upload=json.readTree(response.getResponse().getContentAsString()).path("data");
        var failed=settled(upload.path("runId").asText(),member);
        org.junit.jupiter.api.Assertions.assertEquals("FAILED",failed.path("status").asText());
        org.junit.jupiter.api.Assertions.assertEquals("新闻内容",failed.path("result").path("columns").path(0).asText());
        var body=java.util.Map.of("versionId",upload.path("versionId").asText(),"action","AUDIT","mapping",java.util.Map.of("text","新闻内容"));
        var started=http.perform(csrf(post("/api/workbench/datasets/"+upload.path("datasetId").asText()+"/runs"),member).contentType("application/json").content(json.writeValueAsBytes(body))).andExpect(status().isOk()).andReturn();
        String fixed=json.readTree(started.getResponse().getContentAsString()).path("data").path("runId").asText();finished(fixed,member);
        try(var connection=database.getConnection();var lock=connection.prepareStatement("SELECT GET_LOCK(?,5)")){
            String name=connection.getCatalog()+":dataset-worker";lock.setString(1,name);try(var rs=lock.executeQuery()){org.junit.jupiter.api.Assertions.assertTrue(rs.next() && rs.getInt(1)==1);}
            try{
                var queued=http.perform(csrf(post("/api/workbench/datasets/"+upload.path("datasetId").asText()+"/runs"),member).contentType("application/json").content(json.writeValueAsBytes(body))).andExpect(status().isOk()).andReturn();
                String run=json.readTree(queued.getResponse().getContentAsString()).path("data").path("runId").asText();
                http.perform(csrf(post("/api/workbench/runs/"+run+"/cancel"),member)).andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("CANCELLED"));
                http.perform(get("/api/workbench/runs/"+run).session(member)).andExpect(jsonPath("$.data.status").value("CANCELLED"));
            }finally{try(var release=connection.prepareStatement("SELECT RELEASE_LOCK(?)")){release.setString(1,name);release.execute();}}
        }
    }
}
