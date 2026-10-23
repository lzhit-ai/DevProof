package ai.devproof.infrastructure;

import java.util.Map;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/** The response and business change commit together; callers supply an active transaction. */
@Service
public class CommandStore {
    private final JdbcTemplate jdbc;
    public CommandStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public record Context(String authorization,String method,String path,String key,byte[] rawBody,String correlationId) {}
    public record Result(int status,Map<String,Object> body) {}
    public static Context context(jakarta.servlet.http.HttpServletRequest request,String key,byte[] raw) {
        String correlation=request.getHeader("X-Correlation-Id");
        if(correlation==null || correlation.isBlank())correlation=UUID.randomUUID().toString();
        if(correlation.length()>64)throw new ApiProblem(422,"INPUT_INVALID","关联 ID 不能超过 64 字符");
        return new Context(request.getHeader("Authorization"),request.getMethod(),request.getRequestURI(),key,raw==null?new byte[0]:raw,correlation);
    }
    public Result execute(Context context,int status,Supplier<Map<String,Object>> action) {
        if(context.key()==null || context.key().isBlank() || context.key().length()>128)
            throw new ApiProblem(422,"IDEMPOTENCY_KEY_REQUIRED","请提供不超过 128 字符的 Idempotency-Key");
        String principal=Json.hash(context.authorization()), hash=Json.hash(context.rawBody());
        UUID id=UUID.randomUUID();
        int inserted=jdbc.update("INSERT INTO idempotency_records(id,principal_hash,request_method,request_path,idempotency_key,request_hash,state) VALUES(?,?,?,?,?,?,'IN_PROGRESS') ON CONFLICT(principal_hash,request_method,request_path,idempotency_key) DO NOTHING",
            id,principal,context.method(),context.path(),context.key(),hash);
        if(inserted==0) {
            Map<String,Object> existing=jdbc.queryForMap("SELECT request_hash,state,response_status,response_body::text AS body FROM idempotency_records WHERE principal_hash=? AND request_method=? AND request_path=? AND idempotency_key=? FOR UPDATE",
                principal,context.method(),context.path(),context.key());
            if(!hash.equals(existing.get("request_hash")))throw new ApiProblem(409,"IDEMPOTENCY_CONFLICT","同一幂等键不能对应不同请求内容");
            if(!"COMPLETED".equals(existing.get("state")))throw new ApiProblem(409,"IDEMPOTENCY_IN_PROGRESS","相同命令正在处理中");
            return new Result(((Number)existing.get("response_status")).intValue(),Json.object((String)existing.get("body")));
        }
        Map<String,Object> body=action.get();
        jdbc.update("UPDATE idempotency_records SET state='COMPLETED',response_status=?,response_body=CAST(? AS jsonb),completed_at=clock_timestamp() WHERE id=?",
            status,Json.write(body),id);
        return new Result(status,body);
    }
    /** Authorized callers can replay a completed upload before requiring the compute service. */
    public Result replay(Context context) {
        if(context.key()==null || context.key().isBlank() || context.key().length()>128)
            throw new ApiProblem(422,"IDEMPOTENCY_KEY_REQUIRED","请提供不超过 128 字符的 Idempotency-Key");
        var rows=jdbc.queryForList("SELECT request_hash,state,response_status,response_body::text AS body FROM idempotency_records WHERE principal_hash=? AND request_method=? AND request_path=? AND idempotency_key=?",
            Json.hash(context.authorization()),context.method(),context.path(),context.key());
        if(rows.isEmpty())return null; var row=rows.getFirst();
        if(!Json.hash(context.rawBody()).equals(row.get("request_hash")))throw new ApiProblem(409,"IDEMPOTENCY_CONFLICT","同一幂等键不能对应不同请求内容");
        if(!"COMPLETED".equals(row.get("state")))throw new ApiProblem(409,"IDEMPOTENCY_IN_PROGRESS","相同命令正在处理中");
        return new Result(((Number)row.get("response_status")).intValue(),Json.object((String)row.get("body")));
    }
}
