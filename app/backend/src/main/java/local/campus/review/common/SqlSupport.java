package local.campus.review.common;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import java.sql.Statement;

public final class SqlSupport {
    private SqlSupport() {}
    public static long insert(JdbcTemplate db,String query,Object... values) {
        var key=new GeneratedKeyHolder();
        db.update(connection->{var statement=connection.prepareStatement(query,Statement.RETURN_GENERATED_KEYS);for(int i=0;i<values.length;i++)statement.setObject(i+1,values[i]);return statement;},key);
        if(key.getKey()==null)throw new IllegalStateException("Insert did not return an identity");
        return key.getKey().longValue();
    }
}
