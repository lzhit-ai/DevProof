package ai.devproof.source;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/** Registers source configuration and queues the existing durable synchronization lane. */
@Service
public class ProjectSources {
    private final JdbcTemplate jdbc;
    private final BusinessAudit audit;
    private final BusinessOwnership owners;
    public ProjectSources(JdbcTemplate jdbc,BusinessAudit audit,BusinessOwnership owners) { this.jdbc=jdbc; this.audit=audit; this.owners=owners; }
    public void initializeRepository(UUID project,UUID actor,String raw,String correlation) {
        owners.requireJavaGitHubSources();
        owners.requireJavaGitInputs();
        String slug=UnicodeText.strip(raw);
        while(slug.endsWith("/"))slug=slug.substring(0,slug.length()-1);
        if(slug.startsWith("https://github.com/"))slug=slug.substring(19);
        else if(slug.startsWith("http://github.com/"))slug=slug.substring(18);
        if(slug.endsWith(".git"))slug=slug.substring(0,slug.length()-4);
        if(!slug.matches("[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+") || slug.length()>160)throw new ApiProblem(422,"INPUT_INVALID","GitHub 仓库地址必须是 owner/repository 或 GitHub URL");
        UUID connection=UUID.randomUUID(), repository=UUID.randomUUID(), sync=UUID.randomUUID(); String url="https://github.com/"+slug+".git";
        jdbc.update("INSERT INTO external_connections(id,project_id,provider,name,repository_slug,api_base_url,is_active,created_by) VALUES(?,?,'GITHUB',?,?,'https://api.github.com',true,?)",connection,project,slug,slug,actor);
        jdbc.update("INSERT INTO git_repositories(id,project_id,canonical_url_hash,display_url,read_only) VALUES(?,?,?,?,true)",repository,project,Json.hash(url),url);
        jdbc.update("INSERT INTO source_sync_runs(id,connection_id,requested_by,status,fetched_count,changed_count,page_count,continuation_cursor,attempt_no,max_attempts,executor_owner) VALUES(?,?,?,'RUNNING',0,0,0,'{}',0,3,'JAVA')",sync,connection,actor);
        audit.append(project,actor,"ExternalConnection",connection,"EXTERNAL_CONNECTION_CREATED",correlation,Map.of("provider","GITHUB","repositorySlug",slug),null,null);
        audit.append(project,actor,"GitRepository",repository,"GIT_REPOSITORY_REGISTERED",correlation,Map.of(),null,null);
        audit.append(project,actor,"SourceSyncRun",sync,"SOURCE_SYNC_QUEUED",correlation,Map.of("connectionId",connection.toString()),null,null);
    }
    public void mount(UUID project,UUID actor,List<UUID> bases) {
        if(!bases.isEmpty())owners.requireJavaKnowledgeBases();
        for(UUID base:new LinkedHashSet<>(bases)) {
            if(jdbc.queryForObject("SELECT count(*) FROM knowledge_bases WHERE id=?",Integer.class,base)==0)throw new ApiProblem(404,"RESOURCE_NOT_FOUND","知识库不存在");
            var access=jdbc.queryForList("SELECT p.id FROM projects p JOIN project_members m ON m.project_id=p.id WHERE m.user_id=? AND p.deleted_at IS NULL AND (p.id=(SELECT project_id FROM knowledge_bases WHERE id=?) OR EXISTS(SELECT 1 FROM project_knowledge_bases b WHERE b.project_id=p.id AND b.knowledge_base_id=?)) LIMIT 1 FOR SHARE OF p",actor,base,base);
            if(access.isEmpty())throw new ApiProblem(403,"AUTH_FORBIDDEN","当前用户无法访问该知识库");
            jdbc.update("INSERT INTO project_knowledge_bases(id,project_id,knowledge_base_id,created_by) VALUES(?,?,?,?) ON CONFLICT(project_id,knowledge_base_id) DO NOTHING",UUID.randomUUID(),project,base,actor);
        }
    }
}
