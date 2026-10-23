package local.campus.review.auth;

import org.apache.ibatis.annotations.*;
import java.util.List;

@Mapper
public interface UserMapper {
    record UserRow(Long id,String username,String displayName,String passwordHash,String role,boolean enabled) {}
    @Select("SELECT id,username,display_name,password_hash,role,enabled FROM app_user WHERE username=#{username}")
    UserRow find(String username);
    @Select("SELECT CAST(o.id AS CHAR) AS organizationId,o.name FROM organization o JOIN organization_member m ON m.organization_id=o.id WHERE m.user_id=#{userId} AND m.enabled=true AND o.enabled=true ORDER BY o.id")
    List<CurrentUser.Organization> organizations(long userId);
}
