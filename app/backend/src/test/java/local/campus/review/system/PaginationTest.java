package local.campus.review.system;

import com.fasterxml.jackson.databind.ObjectMapper;
import local.campus.review.auth.*;
import local.campus.review.common.ApiAdvice;
import local.campus.review.workbench.*;
import local.campus.review.content.*;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

class PaginationTest {
    @Test void checkHistorySupportsIndependentPagesAndSubmissionScope()throws Exception{
        var db=new RecordingDatabase();var json=new ObjectMapper();
        CurrentUser[] actor={new CurrentUser("1","创作者",CurrentUser.Role.MEMBER,Set.of("1"),List.of())};
        var users=new CurrentUserService(null){@Override public CurrentUser require(org.springframework.security.core.Authentication authentication){return actor[0];}};
        var service=new InspectionService(db,json,null,null,null,null,null,null);
        var mvc=MockMvcBuilders.standaloneSetup(new InspectionController(service,users,db)).setControllerAdvice(new ApiAdvice()).build();
        for(String kind:List.of("manuscripts","submissions")){
            String path="/api/"+kind+"/9/checks/history";
            var response=mvc.perform(get(path).param("page","7").param("pageSize","7")).andReturn().getResponse();
            assertEquals(200,response.getStatus());var data=json.readTree(response.getContentAsString()).path("data");
            assertEquals(7,data.path("page").asInt());assertEquals(7,data.path("pageSize").asInt());assertEquals(37,data.path("total").asInt());
            assertTrue(db.sql.endsWith("LIMIT ? OFFSET ?"));assertEquals(7,db.args[db.args.length-2]);assertEquals(42L,db.args[db.args.length-1]);
            assertEquals(kind.equals("submissions"),db.sql.contains("submission_version_id=?"));
            assertEquals(400,mvc.perform(get(path).param("pageSize","0")).andReturn().getResponse().getStatus());
        }
        actor[0]=new CurrentUser("2","其他部门",CurrentUser.Role.MEMBER,Set.of("2"),List.of());
        assertEquals(404,mvc.perform(get("/api/manuscripts/9/checks/history")).andReturn().getResponse().getStatus());
        actor[0]=new CurrentUser("3","审核员",CurrentUser.Role.REVIEWER,Set.of(),List.of());
        assertEquals(404,mvc.perform(get("/api/manuscripts/9/checks/history")).andReturn().getResponse().getStatus());
        assertEquals(200,mvc.perform(get("/api/submissions/9/checks/history")).andReturn().getResponse().getStatus());
    }
    @Test void datasetRunHistoryCanReadPastEmbeddedPreviewAndKeepsRoleGuard()throws Exception{
        var db=new RecordingDatabase();var json=new ObjectMapper();
        CurrentUser[] actor={new CurrentUser("1","管理员",CurrentUser.Role.ADMIN,Set.of(),List.of())};
        var users=new CurrentUserService(null){@Override public CurrentUser require(org.springframework.security.core.Authentication authentication){return actor[0];}};
        var service=new DatasetService(db,null,json,new org.springframework.jdbc.datasource.DataSourceTransactionManager());
        var mvc=MockMvcBuilders.standaloneSetup(new DatasetController(service,users)).setControllerAdvice(new ApiAdvice()).build();
        String path="/api/workbench/datasets/00000000-0000-0000-0000-000000000001/runs";
        var response=mvc.perform(get(path).param("page","9").param("pageSize","7")).andReturn().getResponse();
        assertEquals(200,response.getStatus());var data=json.readTree(response.getContentAsString()).path("data");
        assertEquals(9,data.path("page").asInt());assertEquals(7,data.path("pageSize").asInt());assertEquals(37,data.path("total").asInt());
        assertTrue(db.sql.endsWith("LIMIT ? OFFSET ?"));assertEquals(7,db.args[1]);assertEquals(56L,db.args[2]);
        assertEquals(400,mvc.perform(get(path).param("pageSize","101")).andReturn().getResponse().getStatus());
        actor[0]=new CurrentUser("2","创作者",CurrentUser.Role.MEMBER,Set.of(),List.of());
        assertEquals(403,mvc.perform(get(path)).andReturn().getResponse().getStatus());
    }
    @Test void systemListsHonorCustomSizeLargePageAndRejectInvalidPagination()throws Exception{
        var db=new RecordingDatabase();var json=new ObjectMapper();
        var users=new CurrentUserService(null){@Override public CurrentUser require(org.springframework.security.core.Authentication authentication){return new CurrentUser("1","管理员",CurrentUser.Role.ADMIN,Set.of(),List.of());}};
        var mvc=MockMvcBuilders.standaloneSetup(new SystemController(new SystemService(db,json,null,null),users)).setControllerAdvice(new ApiAdvice()).build();
        for(String path:List.of("users","organizations","tasks","logs")){
            var response=mvc.perform(get("/api/system/"+path).param("page",Integer.toString(Integer.MAX_VALUE)).param("pageSize","7")).andReturn().getResponse();
            assertEquals(200,response.getStatus());var data=json.readTree(response.getContentAsString()).path("data");
            assertEquals(7,data.path("pageSize").asInt());assertEquals(Integer.MAX_VALUE,data.path("page").asInt());assertEquals(37,data.path("total").asInt());
            assertTrue(db.sql.endsWith("LIMIT ? OFFSET ?"));assertEquals(7,db.args[db.args.length-2]);assertEquals((Integer.MAX_VALUE-1L)*7,db.args[db.args.length-1]);
            for(String invalid:List.of("0","101","1.5"))assertEquals(400,mvc.perform(get("/api/system/"+path).param("pageSize",invalid)).andReturn().getResponse().getStatus());
            assertEquals(400,mvc.perform(get("/api/system/"+path).param("page","0")).andReturn().getResponse().getStatus());
            var defaults=json.readTree(mvc.perform(get("/api/system/"+path)).andReturn().getResponse().getContentAsString()).path("data");
            assertEquals(20,defaults.path("pageSize").asInt());assertEquals(1,defaults.path("page").asInt());
        }
    }
    private static class RecordingDatabase extends JdbcTemplate {
        String sql;Object[] args;
        @Override public <T>T queryForObject(String sql,Class<T> type,Object... args){return type==Integer.class?type.cast(1):type.cast(37L);}
        @Override public List<Map<String,Object>> queryForList(String sql,Object... args){this.sql=sql;this.args=args;if(sql.equals("SELECT * FROM ml_dataset WHERE id=?")||sql.startsWith("SELECT organization_id FROM manuscript"))return List.of(Map.of("organization_id","1"));if(sql.equals("SELECT manuscript_id FROM submission_version WHERE id=?"))return List.of(Map.of("manuscript_id","8"));return List.of();}
    }
}
