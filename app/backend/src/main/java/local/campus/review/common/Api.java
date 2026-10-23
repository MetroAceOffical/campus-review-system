package local.campus.review.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.*;

public record Api(String code, Object data, String message, Object details, String requestId) {
    public static Api ok(Object data) { return new Api("OK",data,null,null,UUID.randomUUID().toString()); }
    public static Api error(String code,String message) { return new Api(code,null,message,Map.of(),UUID.randomUUID().toString()); }
    public static void writeError(HttpServletResponse response,int status,String code,String message) throws IOException {
        response.setStatus(status); response.setContentType("application/json;charset=UTF-8");
        new ObjectMapper().writeValue(response.getOutputStream(),error(code,message));
    }
}
