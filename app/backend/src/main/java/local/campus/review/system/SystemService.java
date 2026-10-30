package local.campus.review.system;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.*;
import local.campus.review.detection.DetectorClient;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.nio.charset.StandardCharsets;
import java.util.*;

@Service
public class SystemService {
    private final JdbcTemplate db;private final ObjectMapper json;private final PasswordEncoder passwords;private final DetectorClient detector;
    public SystemService(JdbcTemplate db,ObjectMapper json,PasswordEncoder passwords,DetectorClient detector){this.db=db;this.json=json;this.passwords=passwords;this.detector=detector;}
    private ApiException invalid(String message){return new ApiException(400,"VALIDATION_ERROR",message);}
    private void identity(String id){if(id==null || !id.matches("[1-9][0-9]{0,18}"))throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到记录");}
    private void paging(int page,int size,String q){if(page<1 || size<1 || size>100 || q.length()>120)throw invalid("查询参数无效");}
    private String label(String value,int max){if(value==null || value.isBlank() || value.codePointCount(0,value.length())>max)throw invalid("请填写有效名称，最多"+max+"字");return value.strip();}
    private void log(CurrentUser actor,String type,String id,String operation,Object fields){db.update("INSERT INTO operation_log(actor_id,object_type,object_id,operation,details_json,created_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3))",actor.userId(),type,id,operation,JsonSupport.encode(json,fields));}
    public record UserInput(String username,String displayName,String password,String role,Boolean enabled,List<String> organizationIds){}
    private List<String> departments(UserInput input){
        if(input.role()==null || !Set.of("MEMBER","REVIEWER","ADMIN").contains(input.role()))throw invalid("请选择有效角色");
        var ids=input.organizationIds()==null?List.<String>of():input.organizationIds();if(ids.size()>32 || new HashSet<>(ids).size()!=ids.size())throw invalid("部门选择无效");
        for(var id:ids){identity(id);if(db.queryForObject("SELECT COUNT(*) FROM organization WHERE id=? AND enabled=true",Integer.class,id)!=1)throw invalid("请选择启用的部门");}
        if(input.role().equals("MEMBER") && !Boolean.FALSE.equals(input.enabled()) && ids.isEmpty())throw invalid("创作者至少需要一个启用的部门");return ids;
    }
    private void memberships(String id,List<String> organizations){
        db.update("UPDATE organization_member SET enabled=false WHERE user_id=?",id);
        for(var org:organizations)db.update("INSERT INTO organization_member(organization_id,user_id,enabled,joined_at) VALUES(?,?,true,UTC_TIMESTAMP(3)) ON DUPLICATE KEY UPDATE enabled=true",org,id);
    }
    public JsonNode users(CurrentUser actor,int page,String q,String role,String enabled){return users(actor,page,20,q,role,enabled);}
    public JsonNode users(CurrentUser actor,int page,int size,String q,String role,String enabled){
        AccessPolicy.requireAdmin(actor);paging(page,size,q);if(!Set.of("","MEMBER","REVIEWER","ADMIN").contains(role) || !Set.of("","true","false").contains(enabled))throw invalid("筛选条件无效");
        String from=" FROM app_user WHERE (username LIKE ? OR display_name LIKE ?) AND (?='' OR role=?) AND (?='' OR enabled=?)";var args=new ArrayList<Object>(List.of("%"+q+"%","%"+q+"%",role,role,enabled,enabled.equals("true")));
        var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray()));var items=result.putArray("items");args.add(size);args.add((page-1L)*size);
        for(var row:db.queryForList("SELECT CAST(id AS CHAR) AS id,username,display_name AS displayName,role,enabled"+from+" ORDER BY id LIMIT ? OFFSET ?",args.toArray())){var item=json.valueToTree(row);((com.fasterxml.jackson.databind.node.ObjectNode)item).set("organizations",json.valueToTree(db.queryForList("SELECT CAST(o.id AS CHAR) AS id,o.name,o.enabled FROM organization_member m JOIN organization o ON o.id=m.organization_id WHERE m.user_id=? AND m.enabled=true ORDER BY o.id",row.get("id"))));items.add(item);}return result;
    }
    @Transactional public JsonNode saveUser(CurrentUser actor,String id,UserInput input){
        AccessPolicy.requireAdmin(actor);var organizations=departments(input);String name=label(input.displayName(),64);boolean enabled=input.enabled()==null || input.enabled();
        // Serialize administrator changes so simultaneous edits cannot remove the last administrator.
        var admins=db.queryForList("SELECT id FROM app_user WHERE role='ADMIN' AND enabled=true ORDER BY id FOR UPDATE");
        if(id==null){
            if(input.username()==null || !input.username().matches("[A-Za-z0-9][A-Za-z0-9_.-]{2,63}"))throw invalid("账号需为3—64位字母、数字、点、横线或下划线");
            if(input.password()==null || input.password().codePointCount(0,input.password().length())<8 || input.password().getBytes(StandardCharsets.UTF_8).length>72)throw invalid("初始密码至少8位，过长时请缩短");
            if(db.queryForObject("SELECT COUNT(*) FROM app_user WHERE username=?",Integer.class,input.username())>0)throw new ApiException(409,"USERNAME_EXISTS","账号已存在");
            id=Long.toString(SqlSupport.insert(db,"INSERT INTO app_user(username,display_name,password_hash,role,enabled,created_at,updated_at) VALUES(?,?,?,?,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",input.username(),name,passwords.encode(input.password()),input.role(),enabled));memberships(id,organizations);log(actor,"SYSTEM_USER",id,"USER_CREATED",Map.of("username",input.username(),"role",input.role(),"enabled",enabled,"organizationIds",organizations));
        }else{
            identity(id);var rows=db.queryForList("SELECT role,enabled FROM app_user WHERE id=? FOR UPDATE",id);if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到账号");var old=rows.getFirst();
            if(actor.userId().equals(id) && (!enabled || !input.role().equals("ADMIN")))throw new ApiException(409,"SELF_PROTECTION","不能停用当前管理员或修改自身角色");
            if(Boolean.TRUE.equals(old.get("enabled")) && "ADMIN".equals(old.get("role")) && (!enabled || !input.role().equals("ADMIN")) && admins.size()<=1)throw new ApiException(409,"LAST_ADMIN","至少保留一位启用的管理员");
            db.update("UPDATE app_user SET display_name=?,role=?,enabled=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?",name,input.role(),enabled,id);memberships(id,organizations);log(actor,"SYSTEM_USER",id,"USER_UPDATED",Map.of("before",old,"role",input.role(),"enabled",enabled,"organizationIds",organizations));
        }return json.createObjectNode().put("id",id).put("saved",true);
    }
    public JsonNode organizations(CurrentUser actor,int page,String q){return organizations(actor,page,20,q);}
    public JsonNode organizations(CurrentUser actor,int page,int size,String q){
        AccessPolicy.requireAdmin(actor);paging(page,size,q);var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*) FROM organization WHERE name LIKE ?",Long.class,"%"+q+"%"));
        result.set("items",json.valueToTree(db.queryForList("SELECT CAST(o.id AS CHAR) AS id,o.name,o.enabled,(SELECT COUNT(*) FROM organization_member m JOIN app_user u ON u.id=m.user_id WHERE m.organization_id=o.id AND m.enabled=true AND u.enabled=true) AS memberCount,(SELECT COUNT(*) FROM manuscript m WHERE m.organization_id=o.id AND m.deleted_at IS NULL) AS manuscriptCount FROM organization o WHERE o.name LIKE ? ORDER BY o.id LIMIT ? OFFSET ?","%"+q+"%",size,(page-1L)*size)));return result;
    }
    public JsonNode organizationOptions(CurrentUser actor){AccessPolicy.requireAdmin(actor);return json.valueToTree(db.queryForList("SELECT CAST(id AS CHAR) AS id,name,enabled FROM organization ORDER BY id LIMIT 500"));}
    public record OrganizationInput(String name,Boolean enabled){}
    @Transactional public JsonNode saveOrganization(CurrentUser actor,String id,OrganizationInput input){
        AccessPolicy.requireAdmin(actor);String name=label(input.name(),100);boolean enabled=input.enabled()==null || input.enabled();
        if(db.queryForObject("SELECT COUNT(*) FROM organization WHERE name=? AND id<>?",Integer.class,name,id==null?"0":id)>0)throw new ApiException(409,"NAME_EXISTS","部门名称已存在");
        if(id==null){id=Long.toString(SqlSupport.insert(db,"INSERT INTO organization(name,enabled,created_at,updated_at) VALUES(?,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",name,enabled));log(actor,"SYSTEM_DEPARTMENT",id,"DEPARTMENT_CREATED",Map.of("name",name,"enabled",enabled));}
        else{identity(id);var rows=db.queryForList("SELECT name,enabled FROM organization WHERE id=? FOR UPDATE",id);if(rows.isEmpty())throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到部门");
            if(!enabled && db.queryForObject("SELECT COUNT(*) FROM ml_run r JOIN ml_dataset d ON d.id=r.dataset_id WHERE d.organization_id=? AND r.status IN ('QUEUED','RUNNING')",Integer.class,id)>0)throw new ApiException(409,"TASK_ACTIVE","该部门有运行中的数据或训练任务，请完成后再停用");
            db.update("UPDATE organization SET name=?,enabled=?,updated_at=UTC_TIMESTAMP(3) WHERE id=?",name,enabled,id);log(actor,"SYSTEM_DEPARTMENT",id,"DEPARTMENT_UPDATED",Map.of("before",rows.getFirst(),"name",name,"enabled",enabled));
        }return json.createObjectNode().put("id",id).put("saved",true);
    }
    public JsonNode logs(CurrentUser actor,int page,String q){return logs(actor,page,20,q);}
    public JsonNode logs(CurrentUser actor,int page,int size,String q){
        AccessPolicy.requireAdmin(actor);paging(page,size,q);String from=" FROM operation_log l JOIN app_user u ON u.id=l.actor_id WHERE l.object_type IN ('SYSTEM_USER','SYSTEM_DEPARTMENT') AND (u.display_name LIKE ? OR l.operation LIKE ?)";Object[] args={"%"+q+"%","%"+q+"%"};var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,args));
        result.set("items",json.valueToTree(db.queryForList("SELECT CAST(l.id AS CHAR) AS id,u.display_name AS actor,l.object_type AS objectType,CAST(l.object_id AS CHAR) AS objectId,l.operation,l.details_json AS details,DATE_FORMAT(l.created_at,'%Y-%m-%dT%H:%i:%sZ') AS createdAt"+from+" ORDER BY l.id DESC LIMIT ? OFFSET ?",args[0],args[1],size,(page-1L)*size)));return result;
    }
    private static final String TASKS="(SELECT r.id,'DATA' AS kind,r.action,r.status,d.name AS target,r.created_at,r.finished_at FROM ml_run r JOIN ml_dataset d ON d.id=r.dataset_id UNION ALL SELECT c.id,'CHECK' AS kind,c.kind AS action,c.status,CONCAT('稿件 #',c.manuscript_id) AS target,c.created_at,c.finished_at FROM document_check c UNION ALL SELECT CAST(b.id AS CHAR) AS id,'REVIEW' AS kind,'FORMAL' AS action,b.status,CONCAT('送审版本 #',b.submission_version_id) AS target,b.created_at,b.finished_at FROM detection_batch b) t";
    public JsonNode tasks(CurrentUser actor,int page,String q,String status){return tasks(actor,page,20,q,status);}
    public JsonNode tasks(CurrentUser actor,int page,int size,String q,String status){
        AccessPolicy.requireAdmin(actor);paging(page,size,q);if(!Set.of("","ACTIVE","FAILED","COMPLETED","CANCELLED","INTERRUPTED").contains(status))throw invalid("任务状态无效");
        String filter=status.equals("ACTIVE")?" AND t.status IN ('QUEUED','RUNNING','WAITING_SERVICE','WAITING_RESOURCE')":status.isEmpty()?"":" AND t.status=?";String from=" FROM "+TASKS+" WHERE t.target LIKE ?"+filter;var args=new ArrayList<Object>(List.of("%"+q+"%"));if(!status.isEmpty() && !status.equals("ACTIVE"))args.add(status);
        var result=json.createObjectNode().put("page",page).put("pageSize",size).put("total",db.queryForObject("SELECT COUNT(*)"+from,Long.class,args.toArray()));args.add(size);args.add((page-1L)*size);
        result.set("items",json.valueToTree(db.queryForList("SELECT id,kind,action,status,target,DATE_FORMAT(created_at,'%Y-%m-%dT%H:%i:%sZ') AS createdAt,DATE_FORMAT(finished_at,'%Y-%m-%dT%H:%i:%sZ') AS finishedAt"+from+" ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",args.toArray())));return result;
    }
    public JsonNode diagnostics(CurrentUser actor){AccessPolicy.requireAdmin(actor);var result=json.createObjectNode().put("java","READY").put("database",db.queryForObject("SELECT 1",Integer.class)==1?"READY":"UNAVAILABLE");for(var entry:Map.of("detector",false,"ocr",true).entrySet()){var health=detector.health(entry.getValue());result.putObject(entry.getKey()).put("ready",health.path("ready").asBoolean()).put("busy",health.path("busy").asBoolean());}return result;}
}
