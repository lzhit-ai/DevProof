package ai.devproof.source;

import ai.devproof.infrastructure.*;
import java.sql.Timestamp;
import java.time.OffsetDateTime;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Normalizes actual provider resources, preserving historical payload/hash semantics. */
@Component
public class GitHubResourceWriter {
    private final JdbcTemplate jdbc;
    public GitHubResourceWriter(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public record Counts(int fetched,int changed) {}
    public Counts persist(Map<String,Object> connection,UUID actor,GitHubSourceClient.Payload payload) {
        int fetched=0,changed=0;
        for(var batch:List.of(Map.entry("ISSUE",payload.issues()),Map.entry("PULL_REQUEST",payload.pullRequests()),Map.entry("MILESTONE",payload.milestones())))for(Map<String,Object> source:batch.getValue()) {
            Map<String,Object> normalized=normalize(source,batch.getKey()); String key=(String)normalized.get("externalKey");
            String logical="github:"+connection.get("repository_slug")+":"+batch.getKey().toLowerCase(Locale.ROOT)+":"+key;
            jdbc.update("INSERT INTO external_resources(id,connection_id,resource_type,external_key,logical_key) VALUES(?,?,?,?,?) ON CONFLICT(connection_id,resource_type,external_key) DO NOTHING",UUID.randomUUID(),connection.get("id"),batch.getKey(),key,logical);
            Map<String,Object> resource=jdbc.queryForMap("SELECT * FROM external_resources WHERE connection_id=? AND resource_type=? AND external_key=? FOR UPDATE",connection.get("id"),batch.getKey(),key);
            String hash=Json.hash(Json.canonical(normalized)); var revisions=jdbc.queryForList("SELECT * FROM external_resource_revisions WHERE resource_id=? ORDER BY revision_no DESC LIMIT 1",resource.get("id"));
            boolean difference=revisions.isEmpty() || !hash.equals(revisions.getFirst().get("content_hash")); UUID revision;
            if(difference) {
                revision=UUID.randomUUID(); int version=revisions.isEmpty()?1:((Number)revisions.getFirst().get("revision_no")).intValue()+1;
                jdbc.update("INSERT INTO external_resource_revisions(id,resource_id,revision_no,content_hash,title,body,state,web_url,milestone_key,source_updated_at,payload) VALUES(?,?,?,?,?,?,?,?,?,?,CAST(? AS jsonb))",
                    revision,resource.get("id"),version,hash,normalized.get("title"),normalized.get("body"),normalized.get("state"),normalized.get("webUrl"),normalized.get("milestoneKey"),time(normalized.get("sourceUpdatedAt")),Json.canonical(normalized));
            } else revision=(UUID)revisions.getFirst().get("id");
            fetched++; if(difference)changed++;
            if(batch.getKey().equals("PULL_REQUEST")) {
                var existing=jdbc.queryForList("SELECT id FROM delivery_items WHERE project_id=? AND external_key=? FOR UPDATE",connection.get("project_id"),resource.get("logical_key"));
                boolean created=existing.isEmpty(); UUID delivery=created?UUID.randomUUID():(UUID)existing.getFirst().get("id");
                String state=planning((String)normalized.get("state"),(String)normalized.get("stateReason"));
                if(created)jdbc.update("INSERT INTO delivery_items(id,project_id,external_resource_id,external_key,title,planning_status,verification_status,source_updated_at) VALUES(?,?,?,?,?,?,'NOT_ASSESSED',?)",delivery,connection.get("project_id"),resource.get("id"),resource.get("logical_key"),normalized.get("title"),state,time(normalized.get("sourceUpdatedAt")));
                else jdbc.update("UPDATE delivery_items SET external_resource_id=?,title=?,planning_status=?,source_updated_at=?,updated_at=clock_timestamp() WHERE id=?",resource.get("id"),normalized.get("title"),state,time(normalized.get("sourceUpdatedAt")),delivery);
                if(created || difference) {
                    jdbc.update("INSERT INTO delivery_item_source_links(id,delivery_item_id,external_resource_revision_id,link_role,created_by) VALUES(?,?,?,'PRIMARY',?)",UUID.randomUUID(),delivery,revision,actor); changed++;
                }
            }
        }
        return new Counts(fetched,changed);
    }
    private Map<String,Object> normalize(Map<String,Object> item,String kind) {
        if(item.get("number")==null || Objects.toString(item.get("number"),"").isEmpty())throw new ApiProblem(503,"SOURCE_RESPONSE_INVALID","GitHub 资源缺少编号");
        Map<String,Object> result=new LinkedHashMap<>(); result.put("resourceType",kind); result.put("externalKey",item.get("number").toString());
        result.put("title",text(item.get("title"),"")); result.put("body",text(item.get("body"),text(item.get("description"),""))); result.put("state",text(item.get("state"),"UNKNOWN"));
        String merged=text(item.get("merged_at"),""); result.put("stateReason",kind.equals("PULL_REQUEST") && !merged.isEmpty()?"merged":text(item.get("state_reason"),"")); result.put("webUrl",text(item.get("html_url"),""));
        Map<?,?> milestone=item.get("milestone") instanceof Map<?,?> map?map:Map.of(); result.put("milestoneKey",milestone.get("number")==null?null:milestone.get("number").toString());
        result.put("sourceUpdatedAt",text(item.get("updated_at"),"")); List<String> labels=new ArrayList<>();
        if(item.get("labels") instanceof List<?> list)for(Object raw:list)if(raw instanceof Map<?,?> map && map.get("name")!=null && !map.get("name").toString().isEmpty())labels.add(map.get("name").toString());
        result.put("labels",labels); Map<String,Object> pr=null;
        if(kind.equals("PULL_REQUEST")) {
            Map<?,?> base=item.get("base") instanceof Map<?,?> map?map:Map.of(),head=item.get("head") instanceof Map<?,?> map?map:Map.of();
            pr=new LinkedHashMap<>(); pr.put("number",item.get("number").toString()); pr.put("baseRef",text(base.get("ref"),"")); pr.put("baseSha",text(base.get("sha"),""));
            pr.put("headRef",text(head.get("ref"),"")); pr.put("headSha",text(head.get("sha"),"")); pr.put("mergedAt",merged.isEmpty()?null:merged); pr.put("draft",Boolean.TRUE.equals(item.get("draft")));
            Object files=item.get("changed_files"); pr.put("changedFiles",files instanceof Integer || files instanceof Long?files:null);
        }
        result.put("pullRequest",pr); return result;
    }
    private String text(Object value,String fallback) { return value==null || value.toString().isEmpty()?fallback:value.toString(); }
    private String planning(String state,String reason) { return reason.equals("merged")?"DECLARED_DONE":state.equals("closed")?reason.equals("not_planned")?"CANCELLED":"DECLARED_DONE":"OPEN"; }
    private Timestamp time(Object raw) { try { String value=Objects.toString(raw,""); return value.isEmpty()?null:Timestamp.from(OffsetDateTime.parse(value).toInstant()); } catch(java.time.DateTimeException e) { return null; } }
}
