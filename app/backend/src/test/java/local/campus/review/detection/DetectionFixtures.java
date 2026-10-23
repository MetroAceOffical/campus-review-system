package local.campus.review.detection;
import org.springframework.jdbc.core.JdbcTemplate;
import local.campus.review.common.SqlSupport;

final class DetectionFixtures {
    static String version(JdbcTemplate db,String content){
        long user=db.queryForObject("SELECT id FROM app_user WHERE username='member1'",Long.class);
        long manuscript=SqlSupport.insert(db,"INSERT INTO manuscript(organization_id,created_by,created_at,updated_at) VALUES(1,?,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))",user);
        return Long.toString(SqlSupport.insert(db,"INSERT INTO submission_version(manuscript_id,version_no,schema_version,extractor_version,title,content_json,sources_json,plain_text,position_map_json,content_sha256,submitted_by,submitted_at) VALUES(?,1,'1','1','Queue fixture',?,'[]','真实队列测试正文','[]',?,?,UTC_TIMESTAMP(3))",manuscript,content,"a".repeat(64),user));
    }
}
