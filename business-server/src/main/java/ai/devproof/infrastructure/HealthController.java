package ai.devproof.infrastructure;

import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.BadSqlGrammarException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {
    private final JdbcTemplate jdbc;
    public HealthController(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    @GetMapping("/api/v1/health/live") public Map<String, String> live() { return Map.of("status", "ok"); }
    @GetMapping("/api/v1/health/ready") public Map<String, String> ready() {
        jdbc.queryForObject("SELECT 1", Integer.class);
        String expected=ai.devproof.migration.SchemaMigrations.VERSION;
        try {
            var versions=jdbc.queryForList("SELECT version FROM flyway_schema_history WHERE success AND version IS NOT NULL ORDER BY installed_rank DESC LIMIT 1",String.class);
            if(versions.size()!=1 || !expected.equals(versions.getFirst()))
                throw new ApiProblem(503,"SCHEMA_NOT_READY","数据库迁移版本与业务服务不一致");
            var owner=jdbc.queryForList("SELECT owner FROM schema_migration_ownership WHERE id=true",String.class);
            if(owner.size()!=1 || !"FLYWAY".equals(owner.getFirst()) || jdbc.queryForObject("SELECT count(*) FROM business_write_owners WHERE owner='JAVA'",Integer.class)!=ai.devproof.migration.SchemaMigrations.writerCount()
                || jdbc.queryForObject("SELECT count(*) FROM business_write_owners WHERE owner<>'JAVA'",Integer.class)!=0)
                throw new ApiProblem(503,"SCHEMA_NOT_READY","Schema 或业务聚合尚未交接给 Java");
        } catch(BadSqlGrammarException e) {
            throw new ApiProblem(503,"SCHEMA_NOT_READY","业务数据库尚未初始化所需结构");
        }
        return Map.of("status","ready","schemaVersion",expected);
    }
}
