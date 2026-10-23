package ai.devproof.securitybaseline;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class PeripheralStore {
    private static final String GET="SELECT *,input_manifest::text AS manifest_json,output::text AS output_json,coverage::text AS coverage_json,limitations::text AS limitations_json FROM peripheral_profile_runs WHERE project_id=? AND id=?";
    private static final String LIST="SELECT *,input_manifest::text AS manifest_json,output::text AS output_json,coverage::text AS coverage_json,limitations::text AS limitations_json FROM peripheral_profile_runs WHERE project_id=? AND (assessment_profile=? OR CAST(? AS text) IS NULL) ORDER BY created_at DESC,id DESC LIMIT 100";
    private final JdbcTemplate jdbc;
    public PeripheralStore(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public Map<String,Object> create(UUID id,UUID project,String profile,Map<String,Object> manifest,Map<String,Object> output,Map<String,Object> coverage,List<String> limits,UUID actor) {
        jdbc.update("INSERT INTO peripheral_profile_runs(id,project_id,assessment_profile,run_status,input_manifest,input_hash,output,coverage,limitations,created_by) VALUES(?,?,?,'SUCCEEDED',CAST(? AS jsonb),?,CAST(? AS jsonb),CAST(? AS jsonb),CAST(? AS jsonb),?)",id,project,profile,Json.canonical(manifest),Json.hash(Json.canonical(manifest)),Json.canonical(output),Json.canonical(coverage),Json.canonical(limits),actor);
        return view(jdbc.queryForMap(GET,project,id));
    }
    public List<Map<String,Object>> list(UUID project,String profile) { return jdbc.queryForList(LIST,project,profile,profile).stream().map(PeripheralStore::view).toList(); }
    private static Map<String,Object> view(Map<String,Object> row) {
        var view=SecurityStore.fields(row,"id","project_id","assessment_profile","run_status","input_hash","created_at");view.put("input_manifest",SecurityStore.json(row,"manifest_json"));view.put("output",SecurityStore.json(row,"output_json"));view.put("coverage",SecurityStore.json(row,"coverage_json"));view.put("limitations",Json.read((String)row.get("limitations_json")));return view;
    }
}
