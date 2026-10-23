package ai.devproof.infrastructure;

import java.util.Map;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@Service
public class BusinessOwnership {
    private final JdbcTemplate jdbc;
    public BusinessOwnership(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public boolean reportsAreJava() {
        return "JAVA".equals(jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='reports' FOR SHARE",String.class));
    }
    public void requireJavaReports() {
        requireJava("reports");
    }
    public void requireJavaInputs() { requireJava("verification-inputs"); }
    public void requireJavaVerification() { requireJava("verification"); }
    public void requireJavaIdentity() { requireJava("identity"); }
    public void requireJavaProjects() { requireJava("projects"); }
    public void requireJavaTaskManagement() { requireJava("task-management"); }
    public void requireJavaGitHubSources() { requireJava("github-sources"); }
    public void requireJavaKnowledgeBases() { requireJava("knowledge-bases"); }
    public void requireJavaKnowledgeSources() { requireJava("knowledge-sources"); }
    public void requireJavaOrchestration() { requireJava("orchestration"); }
    public void requireJavaEvidenceMaterials() { requireJava("evidence-materials"); }
    public void requireJavaGitInputs() { requireJava("git-inputs"); }
    public void requireJavaDeliveryAssociations() { requireJava("delivery-associations"); }
    public void requireJavaDeliveryClaims() { requireJava("delivery-claims"); }
    public void requireJavaEvidenceQuestions() { requireJava("evidence-questions"); }
    public void requireJavaProjectStatus() { requireJava("project-status"); }
    public void requireJavaSecurityBaselines() { requireJava("security-baselines"); }
    public void requireJavaPeripheralProfiles() { requireJava("peripheral-profiles"); }
    public boolean knowledgeSourcesAreJava() {
        var rows=jdbc.queryForList("SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR SHARE",String.class); return !rows.isEmpty() && "JAVA".equals(rows.getFirst());
    }
    public boolean githubSourcesAreJava() {
        var rows=jdbc.queryForList("SELECT owner FROM business_write_owners WHERE aggregate_key='github-sources' FOR SHARE",String.class); return !rows.isEmpty() && "JAVA".equals(rows.getFirst());
    }
    private void requireJava(String aggregate) {
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key=? FOR SHARE",String.class,aggregate);
        if(!"JAVA".equals(owner))throw new ApiProblem(409,"BUSINESS_OWNER_MISMATCH","该业务聚合尚未交接给 Java");
        jdbc.queryForObject("SELECT set_config('devproof.business_writer','JAVA',true)",String.class);
    }
    @Transactional
    public Map<String,Object> activateReports() {
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='reports' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='reports'");
        return Map.of("aggregate","reports","owner","JAVA");
    }
    @Transactional
    public Map<String,Object> activateVerification() {
        // Reject an active legacy executor before taking an exclusive ownership lock.
        requireLegacyDrained();
        if(!reportsAreJava())throw new ApiProblem(409,"HANDOFF_PRECONDITION","请先交接报告与人工裁决写入方");
        var rows=jdbc.queryForList("SELECT aggregate_key,owner FROM business_write_owners WHERE aggregate_key IN ('verification-inputs','verification') ORDER BY CASE aggregate_key WHEN 'verification-inputs' THEN 0 ELSE 1 END FOR UPDATE");
        if(rows.size()!=2)throw new ApiProblem(503,"SCHEMA_NOT_READY","核验交接配置不完整");
        requireLegacyDrained();
        jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key IN ('verification-inputs','verification') AND owner<>'JAVA'");
        return Map.of("aggregates",java.util.List.of("verification-inputs","verification"),"owner","JAVA");
    }
    private void requireLegacyDrained() {
        Integer active=jdbc.queryForObject("SELECT count(*) FROM analysis_runs r WHERE r.executor_owner='PYTHON' AND r.assessment_profile='DELIVERY_VERIFICATION' AND (r.run_status IN ('QUEUED','RUNNING') OR EXISTS(SELECT 1 FROM analysis_jobs j WHERE j.run_id=r.id AND j.job_status IN ('QUEUED','RUNNING')))",Integer.class);
        if(active!=null && active>0)throw new ApiProblem(409,"LEGACY_RUNS_ACTIVE","存在未结束的旧核验任务，请先完成或取消后交接");
    }
    @Transactional public Map<String,Object> activateIdentity() {
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='identity' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='identity'");
        return Map.of("aggregate","identity","owner","JAVA");
    }
    @Transactional public Map<String,Object> activateManagement() {
        requireJavaVerification(); requireJavaIdentity();
        var rows=jdbc.queryForList("SELECT aggregate_key,owner FROM business_write_owners WHERE aggregate_key IN ('projects','task-management') ORDER BY aggregate_key FOR UPDATE");
        if(rows.size()!=2)throw new ApiProblem(503,"SCHEMA_NOT_READY","项目与任务交接配置不完整");
        jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key IN ('projects','task-management') AND owner<>'JAVA'");
        return Map.of("aggregates",java.util.List.of("projects","task-management"),"owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateGitHubSources() {
        requireJavaProjects();
        String current=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='github-sources'",String.class);
        if("JAVA".equals(current))return Map.of("aggregate","github-sources","owner","JAVA");
        requireLegacySyncDrained();
        jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='github-sources' FOR UPDATE",String.class);
        requireLegacySyncDrained();
        jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='github-sources' AND owner<>'JAVA'");
        return Map.of("aggregate","github-sources","owner","JAVA");
    }
    private void requireLegacySyncDrained() {
        Integer count=jdbc.queryForObject("SELECT count(*) FROM source_sync_runs WHERE executor_owner='PYTHON' AND status='RUNNING' AND lease_owner IS NOT NULL AND (lease_expires_at IS NULL OR lease_expires_at>clock_timestamp())",Integer.class);
        if(count!=null && count>0)throw new ApiProblem(409,"LEGACY_SYNC_ACTIVE","仍有旧 GitHub 同步执行，请等待结束后交接");
    }
    @Transactional(timeout=10) public Map<String,Object> activateKnowledgeBases() {
        requireJavaProjects();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-bases' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='knowledge-bases'");
        return Map.of("aggregate","knowledge-bases","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateKnowledgeSources() {
        requireJavaKnowledgeBases();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-sources'",String.class);
        if("JAVA".equals(owner))return Map.of("aggregate","knowledge-sources","owner","JAVA");
        requireLegacyIngestionDrained();
        jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='knowledge-sources' FOR UPDATE",String.class);
        requireLegacyIngestionDrained();
        jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='knowledge-sources'");
        return Map.of("aggregate","knowledge-sources","owner","JAVA");
    }
    private void requireLegacyIngestionDrained() {
        Integer count=jdbc.queryForObject("SELECT count(*) FROM source_ingestion_jobs WHERE executor_owner='PYTHON' AND job_status='RUNNING' AND (lease_expires_at IS NULL OR lease_expires_at>clock_timestamp())",Integer.class);
        Integer builds=jdbc.queryForObject("SELECT count(*) FROM retrieval_index_build_runs WHERE executor_owner='PYTHON' AND status='RUNNING'",Integer.class);
        if(count!=null && count>0 || builds!=null && builds>0)throw new ApiProblem(409,"LEGACY_INGESTION_ACTIVE","仍有旧资料处理或索引重建执行，请完成后交接");
    }
    @Transactional(timeout=10) public Map<String,Object> activateOrchestration() {
        requireJavaProjects(); requireJavaVerification();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='orchestration' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='orchestration'");
        return Map.of("aggregate","orchestration","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateEvidenceMaterials() {
        requireJavaVerification();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='evidence-materials' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='evidence-materials'");
        return Map.of("aggregate","evidence-materials","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateGitInputs() {
        requireJavaProjects(); requireJavaTaskManagement();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='git-inputs' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='git-inputs'");
        return Map.of("aggregate","git-inputs","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateDeliveryAssociations() {
        requireJavaGitHubSources(); requireJavaGitInputs(); requireJavaTaskManagement();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='delivery-associations' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='delivery-associations'");
        return Map.of("aggregate","delivery-associations","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateDeliveryClaims() {
        requireJavaInputs(); requireJavaTaskManagement(); requireJavaKnowledgeSources(); requireJavaGitHubSources();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='delivery-claims' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='delivery-claims'");
        return Map.of("aggregate","delivery-claims","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateEvidenceQuestions() {
        requireJavaInputs(); requireJavaProjects();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='evidence-questions' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='evidence-questions'");
        return Map.of("aggregate","evidence-questions","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateProjectStatus() {
        requireJavaProjects(); requireJavaTaskManagement(); requireJavaReports(); requireJavaGitHubSources(); requireJavaDeliveryAssociations();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='project-status' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='project-status'");
        return Map.of("aggregate","project-status","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activateSecurityBaselines() {
        requireJavaProjects(); requireJavaGitInputs();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='security-baselines' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='security-baselines'");
        return Map.of("aggregate","security-baselines","owner","JAVA");
    }
    @Transactional(timeout=10) public Map<String,Object> activatePeripheralProfiles() {
        requireJavaProjects(); requireJavaProjectStatus(); requireJavaSecurityBaselines();
        String owner=jdbc.queryForObject("SELECT owner FROM business_write_owners WHERE aggregate_key='peripheral-profiles' FOR UPDATE",String.class);
        if(!"JAVA".equals(owner))jdbc.update("UPDATE business_write_owners SET owner='JAVA',version=version+1,updated_at=clock_timestamp() WHERE aggregate_key='peripheral-profiles'");
        return Map.of("aggregate","peripheral-profiles","owner","JAVA");
    }
    @RestController
    public static class Controller {
        private final BusinessOwnership owners; private final String token;
        public Controller(BusinessOwnership owners,@Value("${devproof.ownership-admin-token:}") String token) { this.owners=owners; this.token=token; }
        @PostMapping("/internal/v1/business-ownership/reports/activate")
        public Map<String,Object> activate(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateReports();
        }
        @PostMapping("/internal/v1/business-ownership/verification/activate")
        public Map<String,Object> verification(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateVerification();
        }
        @PostMapping("/internal/v1/business-ownership/identity/activate")
        public Map<String,Object> identity(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateIdentity();
        }
        @PostMapping("/internal/v1/business-ownership/management/activate")
        public Map<String,Object> management(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateManagement();
        }
        @PostMapping("/internal/v1/business-ownership/github-sources/activate")
        public Map<String,Object> githubSources(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateGitHubSources();
        }
        @PostMapping("/internal/v1/business-ownership/knowledge-bases/activate")
        public Map<String,Object> knowledgeBases(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateKnowledgeBases();
        }
        @PostMapping("/internal/v1/business-ownership/knowledge-sources/activate")
        public Map<String,Object> knowledgeSources(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateKnowledgeSources();
        }
        @PostMapping("/internal/v1/business-ownership/orchestration/activate")
        public Map<String,Object> orchestration(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateOrchestration();
        }
        @PostMapping("/internal/v1/business-ownership/evidence-materials/activate")
        public Map<String,Object> evidenceMaterials(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateEvidenceMaterials();
        }
        @PostMapping("/internal/v1/business-ownership/git-inputs/activate")
        public Map<String,Object> gitInputs(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateGitInputs();
        }
        @PostMapping("/internal/v1/business-ownership/delivery-associations/activate")
        public Map<String,Object> deliveryAssociations(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateDeliveryAssociations();
        }
        @PostMapping("/internal/v1/business-ownership/delivery-claims/activate")
        public Map<String,Object> deliveryClaims(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateDeliveryClaims();
        }
        @PostMapping("/internal/v1/business-ownership/evidence-questions/activate")
        public Map<String,Object> evidenceQuestions(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateEvidenceQuestions();
        }
        @PostMapping("/internal/v1/business-ownership/project-status/activate")
        public Map<String,Object> projectStatus(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateProjectStatus();
        }
        @PostMapping("/internal/v1/business-ownership/security-baselines/activate")
        public Map<String,Object> security(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activateSecurityBaselines();
        }
        @PostMapping("/internal/v1/business-ownership/peripheral-profiles/activate")
        public Map<String,Object> peripheral(@RequestHeader(value="Authorization",required=false) String authorization,@RequestBody Map<String,Object> input) {
            authenticate(authorization); return owners.activatePeripheralProfiles();
        }
        private void authenticate(String authorization) {
            if(token.length()<32)throw new ApiProblem(503,"OWNERSHIP_AUTH_NOT_CONFIGURED","尚未配置业务交接管理凭据");
            String supplied=authorization!=null && authorization.startsWith("Bearer ")?authorization.substring(7):"";
            if(!MessageDigest.isEqual(token.getBytes(StandardCharsets.UTF_8),supplied.getBytes(StandardCharsets.UTF_8)))
                throw new ApiProblem(401,"OWNERSHIP_AUTH_INVALID","业务交接管理身份校验失败");
        }
    }
}
