package local.campus.review.system;

import com.fasterxml.jackson.databind.*;
import local.campus.review.auth.*;
import local.campus.review.common.Api;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.time.*;
import java.util.*;

@RestController
public class DashboardController {
    private final JdbcTemplate db;private final ObjectMapper json;private final CurrentUserService users;
    public DashboardController(JdbcTemplate db,ObjectMapper json,CurrentUserService users){this.db=db;this.json=json;this.users=users;}
    @GetMapping("/api/dashboard") Api get(Authentication auth){
        var user=users.require(auth);boolean member=user.role()==CurrentUser.Role.MEMBER;
        String scope=member?" AND m.organization_id IN (SELECT om.organization_id FROM organization_member om JOIN organization o ON o.id=om.organization_id WHERE om.user_id=? AND om.enabled=true AND o.enabled=true)":"";
        Object[] args=member?new Object[]{user.userId()}:new Object[0];String manuscripts=" FROM manuscript m WHERE m.deleted_at IS NULL"+scope;
        var result=json.createObjectNode().put("generatedAt",Instant.now().toString()).put("scope",member?"所属部门":"全校");var counts=result.putObject("counts");
        counts.put("manuscripts",number("SELECT COUNT(*)"+manuscripts,args)).put("pending",number("SELECT COUNT(*)"+manuscripts+" AND m.status='PENDING'",args)).put("published",number("SELECT COUNT(*)"+manuscripts+" AND m.publication_state='PUBLISHED'",args));
        counts.put("checks",number("SELECT COUNT(*) FROM document_check c JOIN manuscript m ON m.id=c.manuscript_id WHERE m.deleted_at IS NULL"+scope,args));
        if(!member){counts.put("datasets",number("SELECT COUNT(*) FROM ml_dataset WHERE archived=false")).put("models",number("SELECT COUNT(*) FROM ml_model WHERE archived=false")).put("activeRuns",number("SELECT COUNT(*) FROM ml_run WHERE status IN ('QUEUED','RUNNING')")).put("departments",number("SELECT COUNT(*) FROM organization WHERE enabled=true"));}
        result.set("statusDistribution",json.valueToTree(db.queryForList("SELECT m.status,COUNT(*) AS count"+manuscripts+" GROUP BY m.status",args)));
        var days=new TreeMap<String,long[]>();var today=LocalDate.now(ZoneId.of("Asia/Shanghai"));for(int i=13;i>=0;i--)days.put(today.minusDays(i).toString(),new long[2]);
        var dailyArgs=new ArrayList<Object>(Arrays.asList(args));dailyArgs.add(today.minusDays(13).toString());
        String day="DATE(CONVERT_TZ(v.submitted_at,'+00:00','+08:00'))";
        for(var row:db.queryForList("SELECT "+day+" AS day,COUNT(*) AS count FROM submission_version v JOIN manuscript m ON m.id=v.manuscript_id WHERE m.deleted_at IS NULL"+scope+" AND "+day+">=? GROUP BY day",dailyArgs.toArray())){var value=days.get(row.get("day").toString());if(value!=null)value[0]=((Number)row.get("count")).longValue();}
        if(!member)for(var row:db.queryForList("SELECT DATE(CONVERT_TZ(created_at,'+00:00','+08:00')) AS day,COUNT(*) AS count FROM ml_run WHERE DATE(CONVERT_TZ(created_at,'+00:00','+08:00'))>=? GROUP BY day",today.minusDays(13).toString())){var value=days.get(row.get("day").toString());if(value!=null)value[1]=((Number)row.get("count")).longValue();}
        var trend=result.putArray("trend");days.forEach((date,values)->trend.addObject().put("date",date).put("submissions",values[0]).put("runs",values[1]));
        if(member){result.set("recent",json.valueToTree(db.queryForList("SELECT CAST(m.id AS CHAR) AS id,COALESCE(d.title,'未命名草稿') AS title,m.status,m.publication_state AS publicationState,CAST(m.current_submission_id AS CHAR) AS submissionId,DATE_FORMAT(m.updated_at,'%Y-%m-%dT%H:%i:%sZ') AS updatedAt FROM manuscript m LEFT JOIN manuscript_draft d ON d.manuscript_id=m.id WHERE m.deleted_at IS NULL"+scope+" ORDER BY m.updated_at DESC,m.id DESC LIMIT 8",args)));}
        else if(user.role()==CurrentUser.Role.REVIEWER){result.set("recent",json.valueToTree(db.queryForList("SELECT CAST(v.id AS CHAR) AS id,v.title,m.status,DATE_FORMAT(v.submitted_at,'%Y-%m-%dT%H:%i:%sZ') AS updatedAt FROM submission_version v JOIN manuscript m ON m.current_submission_id=v.id WHERE m.deleted_at IS NULL AND m.status='PENDING' ORDER BY v.submitted_at DESC LIMIT 8")));}
        else result.set("recent",json.createArrayNode());
        if(!member)result.set("runs",json.valueToTree(db.queryForList("SELECT r.id,r.action,r.status,d.name AS title,DATE_FORMAT(r.created_at,'%Y-%m-%dT%H:%i:%sZ') AS createdAt FROM ml_run r JOIN ml_dataset d ON d.id=r.dataset_id ORDER BY (r.status IN ('RUNNING','QUEUED')) DESC,r.created_at DESC LIMIT 8")));
        return Api.ok(result);
    }
    private long number(String sql,Object... args){return Objects.requireNonNull(db.queryForObject(sql,Long.class,args));}
}
