package local.campus.review.content;

import local.campus.review.HttpTestSupport;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.mock.web.MockMultipartFile;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.sql.Statement;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=${CAMPUS_TEST_DB_URL}","spring.datasource.username=${CAMPUS_TEST_DB_USER}","spring.datasource.password=${CAMPUS_TEST_DB_PASSWORD}"})
@AutoConfigureMockMvc(print=MockMvcPrint.NONE)
class FileAccessIT extends HttpTestSupport {
    @Autowired JdbcTemplate sql;
    byte[] png() throws Exception {var out=new ByteArrayOutputStream();ImageIO.write(new BufferedImage(20,10,BufferedImage.TYPE_INT_RGB),"png",out);return out.toByteArray();}
    @Test void uploadLimitAndDecodedFormat() throws Exception {
        var session=login("member1");
        http.perform(csrf(multipart("/api/files").file(new MockMultipartFile("file","evil.jpg","image/jpeg","<svg/>".getBytes())),session)).andExpect(status().isUnsupportedMediaType());
        http.perform(csrf(multipart("/api/files").file(new MockMultipartFile("file","large.png","image/png",new byte[10485761])),session)).andExpect(status().isPayloadTooLarge());
        http.perform(csrf(multipart("/api/files").file(new MockMultipartFile("file","renamed.bin","application/octet-stream",png())),session))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.mimeType").value("image/png"));
    }
    @Test void evidenceFileIsNotMemberBodyFile() throws Exception {
        var member=login("member1");var other=login("member2");var reviewer=login("reviewer");
        var upload=http.perform(csrf(multipart("/api/files").file(new MockMultipartFile("file","probe.png","image/png",png())),member)).andExpect(status().isOk()).andReturn();
        var fileId=json.readTree(upload.getResponse().getContentAsString()).path("data").path("fileId").asText();
        http.perform(get("/api/files/"+fileId).session(other)).andExpect(status().isNotFound());
        var created=http.perform(csrf(post("/api/manuscripts"),member).contentType("application/json").content("{\"organizationId\":\"1\"}"))
            .andExpect(status().isOk()).andReturn();
        var manuscriptId=json.readTree(created.getResponse().getContentAsString()).path("data").path("manuscriptId").asText();
        var key=new GeneratedKeyHolder();
        sql.update(connection->{var s=connection.prepareStatement("INSERT INTO submission_version(manuscript_id,version_no,schema_version,extractor_version,title,content_json,sources_json,plain_text,position_map_json,content_sha256,lifecycle_status,submitted_by,submitted_at) SELECT ?,1,'1','1','权限夹具',JSON_OBJECT('type','doc'),JSON_ARRAY(),'',JSON_ARRAY(),REPEAT('0',64),'PENDING',id,UTC_TIMESTAMP(3) FROM app_user WHERE username='member1'",Statement.RETURN_GENERATED_KEYS);s.setString(1,manuscriptId);return s;},key);
        sql.update("INSERT INTO file_binding(file_id,submission_version_id,node_id,purpose) VALUES(?,?,'evidence','EVIDENCE_IMAGE')",fileId,key.getKey());
        http.perform(get("/api/files/"+fileId).session(member)).andExpect(status().isNotFound());
        http.perform(get("/api/files/"+fileId).session(reviewer)).andExpect(status().isOk());
    }
}
