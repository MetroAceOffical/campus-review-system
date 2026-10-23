package local.campus.review.bootstrap;

import com.fasterxml.jackson.databind.ObjectMapper;
import javax.sql.DataSource;
import java.nio.file.*;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class Bootstrap implements ApplicationRunner {
    private final DataSource db;
    private final JdbcTemplate sql;
    private final PasswordEncoder passwords;
    private final ObjectMapper json;
    public Bootstrap(DataSource db,JdbcTemplate sql,PasswordEncoder passwords,ObjectMapper json) {this.db=db;this.sql=sql;this.passwords=passwords;this.json=json;}
    @Override public void run(ApplicationArguments args) throws Exception {
        var migrations=System.getenv("CAMPUS_MIGRATIONS");
        if(migrations==null) throw new IllegalStateException("CAMPUS_MIGRATIONS must point to project migrations");
        try(var connection=db.getConnection()) { MigrationRunner.apply(connection,Path.of(migrations)); }
        var accountsFile=System.getenv("CAMPUS_ACCOUNTS_FILE");
        if(accountsFile==null) throw new IllegalStateException("Initialize project account credentials before startup");
        var accounts=json.readTree(Files.readString(Path.of(accountsFile)));
        String[][] rows={{"member1","学生会投稿成员","MEMBER"},{"member2","融媒体投稿成员","MEMBER"},{"reviewer","审核员","REVIEWER"},{"admin","管理员","ADMIN"}};
        for(var row:rows) {
            if(sql.queryForObject("SELECT COUNT(*) FROM app_user WHERE username=?",Integer.class,row[0])==0) {
                if(!accounts.hasNonNull(row[0]) || accounts.path(row[0]).asText().length()<16) throw new IllegalStateException("Missing strong initial account password");
                sql.update("INSERT INTO app_user(username,display_name,password_hash,role,enabled,created_at,updated_at) VALUES(?,?,?,?,true,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",row[0],row[1],passwords.encode(accounts.path(row[0]).asText()),row[2]);
            }
        }
        seedOrganization(1,"校学生会","member1"); seedOrganization(2,"校园融媒体中心","member2");
    }
    private void seedOrganization(long id,String name,String username) {
        sql.update("INSERT IGNORE INTO organization(id,name,enabled,created_at,updated_at) VALUES(?,?,true,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",id,name);
        sql.update("INSERT IGNORE INTO organization_member(organization_id,user_id,enabled,joined_at) SELECT ?,id,true,UTC_TIMESTAMP(3) FROM app_user WHERE username=?",id,username);
    }
}
