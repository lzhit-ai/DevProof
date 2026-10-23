package ai.devproof.infrastructure;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class BusinessAudit {
    private final JdbcTemplate jdbc;
    public BusinessAudit(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public void append(UUID project,UUID actor,String type,UUID id,String action,String correlation,Map<String,Object> payload,Integer before,Integer after) {
        jdbc.update("INSERT INTO audit_events(id,project_id,actor_id,aggregate_type,aggregate_id,action,correlation_id,payload,before_version,after_version) VALUES(?,?,?,?,?,?,?,CAST(? AS jsonb),?,?)",
            UUID.randomUUID(),project,actor,type,id,action,correlation,Json.write(payload),before,after);
    }
}
