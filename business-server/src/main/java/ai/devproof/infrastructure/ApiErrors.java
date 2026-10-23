package ai.devproof.infrastructure;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(ApiProblem.class)
    public ResponseEntity<?> problem(ApiProblem e, HttpServletRequest request) {
        return ResponseEntity.status(e.status).body(Json.error(e.code, e.getMessage(), request.getHeader("X-Correlation-Id")));
    }
    @ExceptionHandler({MethodArgumentNotValidException.class, MethodArgumentTypeMismatchException.class,
            org.springframework.http.converter.HttpMessageNotReadableException.class,
            tools.jackson.core.JacksonException.class, java.time.format.DateTimeParseException.class,
            org.springframework.web.bind.MissingRequestHeaderException.class})
    public ResponseEntity<?> input(Exception e, HttpServletRequest request) {
        return problem(new ApiProblem(422, "INPUT_INVALID", "请求参数不符合约束"), request);
    }
    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<?> database(DataAccessException e, HttpServletRequest request) {
        return problem(new ApiProblem(503, "DATABASE_UNAVAILABLE", "业务数据库当前不可用"), request);
    }
    @ExceptionHandler(org.springframework.web.multipart.MaxUploadSizeExceededException.class)
    public ResponseEntity<?> uploadSize(Exception e,HttpServletRequest request) {
        return problem(new ApiProblem(413,"SOURCE_TOO_LARGE","上传资料超过配置的大小上限"),request);
    }
    @ExceptionHandler({org.springframework.web.multipart.MultipartException.class,org.springframework.web.bind.MissingServletRequestParameterException.class})
    public ResponseEntity<?> multipart(Exception e,HttpServletRequest request) { return problem(new ApiProblem(422,"INPUT_INVALID","上传资料或表单字段不符合约束"),request); }
}
