package local.campus.review.workbench;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.bootstrap.MigrationRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.*;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class AutomaticPipelineTest {
    final ObjectMapper json=new ObjectMapper();
    @Test void newsBlocksUntilPreparedAndEachModelEvaluatesOnce() throws Exception {
        var config=json.readTree("{\"kind\":\"NEWS\",\"evaluate\":true,\"models\":[{\"family\":\"cnn\"},{\"family\":\"bert\"}]}");
        var state=AutomaticPipelineService.initial(json,false,"version");
        AutomaticPipelineService.consume(state,config,json.createObjectNode(),Map.of("id","groups"));
        assertEquals("GENERATE",state.path("stage").asText());
        AutomaticPipelineService.consume(state,config,json.createObjectNode().put("trainReady",false),Map.of("id","samples"));
        assertEquals("BLOCKED",state.path("stage").asText());
        state.put("stage","TRAIN");
        for(int i=0;i<2;i++){
            AutomaticPipelineService.consume(state,config,json.createObjectNode(),Map.of("id","model"+i));
            assertEquals("EVALUATE",state.path("stage").asText());
            AutomaticPipelineService.consume(state,config,json.createObjectNode(),Map.of("id","eval"+i));
        }
        assertEquals("DONE",state.path("stage").asText());assertEquals(2,state.path("models").size());
        assertEquals("eval1",state.path("models").get(1).path("evaluationRunId").asText());
    }
    @Test void invalidModelsAndCreatorAreRejected(){
        assertThrows(ApiException.class,()->AutomaticPipelineService.validateModels(List.of(new AutomaticPipelineService.Model(null,null))));
        assertThrows(ApiException.class,()->AutomaticPipelineService.validateModels(List.of(new AutomaticPipelineService.Model("cnn",null),new AutomaticPipelineService.Model("cnn",null))));
        var data=new DatasetService(null,null,json,new DataSourceTransactionManager());
        assertThrows(ApiException.class,()->new AutomaticPipelineService(data,null,null,false).create(new CurrentUser("1","创作者",CurrentUser.Role.MEMBER,Set.of(),List.of()),null));
    }
    @Test void actualCpuPipelineSurvivesDispatcherRestartWithoutDuplicateJobs() throws Exception {
        String url=System.getenv("CAMPUS_TEST_DB_URL");Assumptions.assumeTrue(url!=null);
        assertTrue(url.contains("/campus_review_midterm_test?"));assertEquals("test",System.getenv("CAMPUS_RUNTIME_NAMESPACE"));
        var settings=new RuntimeSettings(json);
        var ds=new DriverManagerDataSource(url,System.getenv("CAMPUS_TEST_DB_USER"),System.getenv("CAMPUS_TEST_DB_PASSWORD"));
        try(var connection=ds.getConnection()){MigrationRunner.apply(connection,settings.root().resolve("app/backend/src/main/resources/db/migrations"));}
        var db=new JdbcTemplate(ds);var data=new DatasetService(db,settings,json,new DataSourceTransactionManager(ds));var training=new TrainingService(data);
        var users=new CurrentUserService(new UserMapper(){
            public UserRow find(String name){return db.queryForObject("SELECT * FROM app_user WHERE username=?",(r,n)->new UserRow(r.getLong("id"),r.getString("username"),r.getString("display_name"),r.getString("password_hash"),r.getString("role"),r.getBoolean("enabled")),name);}
            public List<CurrentUser.Organization> organizations(long id){return db.query("SELECT CAST(o.id AS CHAR) AS organization_id,o.name FROM organization o JOIN organization_member m ON m.organization_id=o.id WHERE m.user_id=? AND m.enabled=true AND o.enabled=true",(r,n)->new CurrentUser.Organization(r.getString(1),r.getString(2)),id);}
        });
        String username=db.queryForObject("SELECT username FROM app_user WHERE role='ADMIN' AND enabled=true LIMIT 1",String.class);
        var actor=users.require(UsernamePasswordAuthenticationToken.authenticated(username,null,List.of()));
        String organization=db.queryForObject("SELECT CAST(id AS CHAR) FROM organization WHERE enabled=true LIMIT 1",String.class);
        var csv=new StringBuilder("id,sentence1,sentence2,label,group_id\n");
        for(int g=0;g<30;g++)for(int label=0;label<2;label++)csv.append(g).append('-').append(label).append(",学院新闻").append(g).append("本次讲座介绍校园活动,学院新闻").append(g).append(label==1?"本次讲座介绍校园活动":"讨论完全不同的科研实验").append(',').append(label).append(',').append(g).append('\n');
        var uploaded=data.upload(actor,organization,"阶段16 CPU工程检查","PAIRS",new MockMultipartFile("file","pipeline.csv","text/csv",csv.toString().getBytes(StandardCharsets.UTF_8)));
        String dataset=uploaded.path("datasetId").asText(),version=uploaded.path("versionId").asText();data.cancel(actor,uploaded.path("runId").asText());
        var pipelines=new AutomaticPipelineService(data,training,users,false);
        var sixModels=List.of("lr","svm","rf","cnn","bilstm","bert").stream().map(f->new AutomaticPipelineService.Model(f,json.createObjectNode().put("device","cpu").put("max_iter",100).put("epochs",1).put("max_length",16).put("batch_size",8).put("width",16))).toList();
        var created=pipelines.create(actor,new AutomaticPipelineService.Create(dataset,version,"CPU链路检查",null,null,json.readTree("{\"seed\":20261028,\"ratios\":[0.8,0.1,0.1]}"),null,sixModels,true));
        String id=created.path("pipelineId").asText();var actions=new ArrayList<String>();
        var worker=new WorkbenchWorker(data,false);var compute=new TrainingWorker(training,false);
        try{
            for(int phase=0;phase<14;phase++){
                pipelines.advance(id);var view=pipelines.get(actor,id);assertEquals("RUNNING",view.path("status").asText(),view.toString());
                String run=view.path("state").path("currentRunId").asText();pipelines.advance(id);
                assertEquals(run,pipelines.get(actor,id).path("state").path("currentRunId").asText());
                assertEquals(1,db.update("UPDATE ml_run SET status='RUNNING',started_at=UTC_TIMESTAMP(3) WHERE id=? AND status='QUEUED'",run));
                var job=data.runRow(actor,run);String action=job.get("action").toString();actions.add(action);
                Object target=action.equals("CLEAN")?worker:compute;
                var execute=target.getClass().getDeclaredMethod("execute",Map.class);execute.setAccessible(true);
                try{execute.invoke(target,job);}catch(java.lang.reflect.InvocationTargetException e){throw new AssertionError("Child "+action+" "+run,e.getCause());}
                assertEquals("COMPLETED",data.runRow(actor,run).get("status"));
                pipelines=new AutomaticPipelineService(data,training,users,false);
            }
            pipelines.advance(id);var completed=pipelines.get(actor,id);assertEquals("COMPLETED",completed.path("status").asText(),completed.toString());
            pipelines.advance(id);assertEquals(14,pipelines.get(actor,id).path("state").path("steps").size());
            var expected=new ArrayList<>(List.of("CLEAN","PREPARE"));for(int member=0;member<6;member++)expected.addAll(List.of("TRAIN","EVALUATE"));assertEquals(expected,actions);
            var repeat=new AutomaticPipelineService.Create(dataset,version,"取消重试工程检查",null,null,null,null,sixModels,true);
            String cancelled=pipelines.create(actor,repeat).path("pipelineId").asText();pipelines.advance(cancelled);
            String old=pipelines.get(actor,cancelled).path("state").path("currentRunId").asText();
            pipelines.control(actor,cancelled,false);assertEquals("CANCELLED",data.runRow(actor,old).get("status"));
            pipelines.control(actor,cancelled,true);pipelines.advance(cancelled);
            String replacement=pipelines.get(actor,cancelled).path("state").path("currentRunId").asText();assertNotEquals(old,replacement);
            pipelines.control(actor,cancelled,false);
            var noLongerAuthorized=new CurrentUserService(new UserMapper(){
                public UserRow find(String name){return new UserRow(Long.valueOf(actor.userId()),name,"权限变更检查","","MEMBER",true);}
                public List<CurrentUser.Organization> organizations(long id){return List.of();}
            });
            String revoked=pipelines.create(actor,repeat).path("pipelineId").asText();
            new AutomaticPipelineService(data,training,noLongerAuthorized,false).advance(revoked);
            assertEquals("FAILED",pipelines.get(actor,revoked).path("status").asText());
            assertEquals(0,pipelines.get(actor,revoked).path("state").path("steps").size());
            var evidence=json.createObjectNode().put("pipelineId",id).put("datasetId",dataset).put("status","COMPLETED").put("device","cpu").put("formalTraining",false).put("dispatcherRestartAfterEveryStage",true).put("duplicateDispatch",false);
            evidence.put("cancelRetryCreatesNewJob",true).put("reauthorizationBeforeDispatch",true);
            evidence.set("result",completed);Files.createDirectories(settings.root().resolve("runtime/workbench-implementation"));
            Files.writeString(settings.root().resolve("runtime/workbench-implementation/stage16-pipeline-check.json"),json.writerWithDefaultPrettyPrinter().writeValueAsString(evidence));
        }finally{worker.close();compute.close();}
    }
}
