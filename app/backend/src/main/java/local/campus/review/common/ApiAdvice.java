package local.campus.review.common;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
public class ApiAdvice {
    @ExceptionHandler(org.springframework.web.multipart.MaxUploadSizeExceededException.class)
    ResponseEntity<Api> oversized(Exception e) {return ResponseEntity.status(413).body(Api.error("UPLOAD_TOO_LARGE","单图不能超过10MiB"));}
    @ExceptionHandler(ApiException.class)
    ResponseEntity<Api> business(ApiException e) { return ResponseEntity.status(e.status).body(Api.error(e.code,e.getMessage())); }
    @ExceptionHandler({HttpMessageNotReadableException.class,IllegalArgumentException.class})
    ResponseEntity<Api> invalid(Exception e) { return ResponseEntity.badRequest().body(Api.error("VALIDATION_ERROR","请求内容无效，请检查填写内容")); }
    @ExceptionHandler(org.springframework.dao.DataAccessException.class)
    ResponseEntity<Api> database(Exception e) { return ResponseEntity.status(503).body(Api.error("DATABASE_UNAVAILABLE","数据保存或读取未完成，请稍后重试")); }
}
