package local.campus.review.common;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice
public class ApiAdvice {
    @ExceptionHandler(ApiException.class)
    ResponseEntity<Api> business(ApiException e) { return ResponseEntity.status(e.status).body(Api.error(e.code,e.getMessage())); }
    @ExceptionHandler({HttpMessageNotReadableException.class,IllegalArgumentException.class})
    ResponseEntity<Api> invalid(Exception e) { return ResponseEntity.badRequest().body(Api.error("VALIDATION_ERROR","请求内容无效，请检查填写内容")); }
}
