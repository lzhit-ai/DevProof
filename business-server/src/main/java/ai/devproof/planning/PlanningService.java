package ai.devproof.planning;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import ai.devproof.project.ProjectAccess;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlanningService {
    private final PlanningMapper data;
    private final ProjectAccess access;
    private final RepositorySnapshotService repositories;
    private final PlanningTaskFactory tasks;
    private final PlanValidator validator;
    public PlanningService(PlanningMapper data,ProjectAccess access,RepositorySnapshotService repositories,PlanningTaskFactory tasks,PlanValidator validator) {
        this.data=data; this.access=access; this.repositories=repositories; this.tasks=tasks; this.validator=validator;
    }
    public List<Map<String,Object>> list(UUID projectId,UUID actorId) { access.require(projectId,actorId); return data.ideas(projectId); }
    public Map<String,Object> permissions(UUID projectId,UUID actorId) {
        String role=access.role(projectId,actorId);
        return Map.of("role",role,"canPlan",Set.of("SUBMITTER","ADMIN").contains(role),"canConfirm",Set.of("REVIEWER","ADMIN").contains(role));
    }
    @Transactional
    public Map<String,Object> create(UUID projectId,UUID actorId,String title,String content) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN");
        UUID id=UUID.randomUUID(); data.createIdea(id,projectId,title.strip(),actorId);
        data.revision(UUID.randomUUID(),id,1,content.strip(),actorId);
        return detail(projectId,id,actorId);
    }
    public Map<String,Object> detail(UUID projectId,UUID ideaId,UUID actorId) {
        access.require(projectId,actorId); Map<String,Object> idea=require(data.idea(projectId,ideaId));
        Map<String,Object> revision=data.latestRevision(ideaId), run=data.latestRun((UUID)revision.get("id"));
        Map<String,Object> result=new LinkedHashMap<>(); result.put("idea",idea); result.put("revision",revision);
        result.put("questions",data.questions((UUID)revision.get("id"))); result.put("latestRun",run);
        result.put("agentTask",run==null?null:data.taskForRun((UUID)run.get("id")));
        result.put("plans",data.plans(ideaId).stream().map(this::projectPlan).toList()); return result;
    }
    @Transactional
    public Map<String,Object> revise(UUID projectId,UUID ideaId,UUID actorId,int expected,String title,String content) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN"); Map<String,Object> idea=require(data.lockIdea(projectId,ideaId));
        if (((Number)idea.get("version")).intValue()!=expected) throw conflict("Idea 已被其他人修改");
        Map<String,Object> active=data.latestRun((UUID)data.latestRevision(ideaId).get("id"));
        if (active!=null && Set.of("QUEUED","RUNNING").contains(active.get("status"))) throw conflict("请先取消当前规划运行再修改 Idea");
        data.reviseIdea(ideaId,title.strip()); data.revision(UUID.randomUUID(),ideaId,expected+1,content.strip(),actorId);
        return detail(projectId,ideaId,actorId);
    }
    @Transactional
    public Map<String,Object> start(UUID projectId,UUID ideaId,UUID actorId,UUID repositorySnapshotId,int expected,String requestKey) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN"); Map<String,Object> idea=require(data.lockIdea(projectId,ideaId));
        String requestHash=Json.hash(Json.write(Map.of("operation","START","ideaId",ideaId,"snapshotId",repositorySnapshotId,"expectedVersion",expected)));
        Map<String,Object> replay=replay(projectId,actorId,requestKey,requestHash); if(replay!=null)return replay;
        if (((Number)idea.get("version")).intValue()!=expected) throw conflict("Idea 已变更，请读取最新修订后再规划");
        return enqueue(projectId,idea,actorId,repositorySnapshotId,"PLAN_DRAFT",requestKey,requestHash);
    }
    @Transactional
    public Map<String,Object> answers(UUID projectId,UUID ideaId,UUID actorId,List<Answer> answers,String requestKey) {
        access.require(projectId,actorId,"SUBMITTER","ADMIN"); Map<String,Object> idea=require(data.lockIdea(projectId,ideaId));
        String requestHash=Json.hash(Json.write(Map.of("operation","ANSWERS","ideaId",ideaId,"answers",answers)));
        Map<String,Object> replay=replay(projectId,actorId,requestKey,requestHash); if(replay!=null)return replay;
        Map<String,Object> revision=data.latestRevision(ideaId), run=require(data.latestRun((UUID)revision.get("id")));
        if (!"SUCCEEDED".equals(run.get("status"))) throw conflict("当前没有等待回答的已完成规划运行");
        UUID runId=(UUID)run.get("id");
        List<Map<String,Object>> questions=data.questions((UUID)revision.get("id"));
        Map<UUID,Map<String,Object>> byId=new HashMap<>();
        for(Map<String,Object> question:questions) if(runId.equals(question.get("planning_run_id")))byId.put((UUID)question.get("id"),question);
        Set<UUID> seen=new HashSet<>();
        for(Answer answer:answers) {
            Map<String,Object> question=byId.get(answer.questionId());
            if(question==null || !seen.add(answer.questionId())) throw new ApiProblem(422,"QUESTION_INVALID","问题不属于当前规划运行或重复提交");
            if(question.get("answer")!=null) {
                if(!answer.answer().strip().equals(question.get("answer"))) throw conflict("已回答问题请通过新 Idea 修订调整");
            } else if(data.answer(answer.questionId(),runId,answer.answer().strip(),actorId)!=1)throw conflict("问题已被其他人回答");
        }
        if(data.questions((UUID)revision.get("id")).stream().anyMatch(question->runId.equals(question.get("planning_run_id")) && question.get("answer")==null))
            return Map.of("needsMoreAnswers",true);
        Map<String,Object> input=data.inputById((UUID)run.get("snapshot_id"));
        return enqueue(projectId,idea,actorId,(UUID)input.get("repository_snapshot_id"),"PLAN_REFINE",requestKey,requestHash);
    }
    public record Answer(UUID questionId,String answer) {}
    private Map<String,Object> enqueue(UUID projectId,Map<String,Object> idea,UUID actorId,UUID repoId,String kind,String requestKey,String requestHash) {
        UUID ideaId=(UUID)idea.get("id"); Map<String,Object> revision=data.latestRevision(ideaId);
        UUID revisionId=(UUID)revision.get("id"); Map<String,Object> active=data.latestRun(revisionId);
        if(active!=null && Set.of("QUEUED","RUNNING").contains(active.get("status")))throw conflict("已有规划运行排队或执行中");
        Map<String,Object> repoRow=repositories.load(projectId,repoId), repository=Json.object((String)repoRow.get("body_json"));
        List<Map<String,Object>> answers=new ArrayList<>();
        for(Map<String,Object> question:data.questions(revisionId)) if(question.get("answer")!=null)
            answers.add(Map.of("questionId",question.get("id").toString(),"question",question.get("question"),"answer",question.get("answer")));
        Map<String,Object> input=new LinkedHashMap<>();
        input.put("schemaVersion","planning-input-v1");
        input.put("idea",Map.of("id",ideaId.toString(),"revisionId",revisionId.toString(),"revisionNo",revision.get("revision_no"),"title",idea.get("title"),"content",revision.get("content")));
        input.put("clarifications",answers);
        Map<String,Object> previous=data.plans(ideaId).stream().filter(plan->"CONFIRMED".equals(plan.get("status"))).findFirst().orElse(null);
        input.put("previousPlan",previous==null?null:Map.of("id",previous.get("id").toString(),"contentHash",previous.get("content_hash"),"body",Json.object((String)previous.get("body_json"))));
        input.put("repositorySnapshot",Map.of("id",repoId.toString(),"contentHash",repoRow.get("content_hash"),"targetSha",repoRow.get("target_sha"),"repositoryId",repoRow.get("repository_id").toString()));
        String frozen=Json.write(input), hash=Json.hash(frozen); UUID inputId=UUID.randomUUID(), runId=UUID.randomUUID();
        data.input(inputId,projectId,repoId,hash,frozen,actorId); data.run(runId,projectId,inputId,revisionId,actorId,requestKey,requestHash);
        UUID taskId=tasks.enqueue(projectId,actorId,runId,inputId,hash,repository,kind);
        return Map.of("runId",runId,"taskId",taskId,"status","QUEUED");
    }
    private Map<String,Object> replay(UUID projectId,UUID actorId,String key,String hash) {
        if(key==null || key.isBlank() || key.length()>200)throw new ApiProblem(422,"IDEMPOTENCY_KEY_REQUIRED","请提供有效的 Idempotency-Key");
        Map<String,Object> run=data.byRequest(projectId,actorId,key);
        if(run==null)return null;
        if(!hash.equals(run.get("request_hash")))throw new ApiProblem(409,"IDEMPOTENCY_CONFLICT","同一幂等键不能对应不同请求");
        Map<String,Object> task=data.taskForRun((UUID)run.get("id"));
        return Map.of("runId",run.get("id"),"taskId",task.get("id"),"status",task.get("status"));
    }
    @Transactional
    public Map<String,Object> edit(UUID projectId,UUID planId,UUID actorId,int expected,Map<String,Object> body) {
        Map<String,Object> plan=lockedPlan(projectId,planId,actorId,"SUBMITTER","ADMIN");
        if(!"DRAFT".equals(plan.get("status")))throw conflict("已确认计划须创建新版本后修改");
        if(((Number)plan.get("version")).intValue()!=expected)throw conflict("计划草案已被其他人修改");
        validateBody(plan,body); String json=Json.write(body); data.editPlan(planId,json,Json.hash(json));
        return projectPlan(data.planContext(planId));
    }
    @Transactional
    public Map<String,Object> newVersion(UUID projectId,UUID planId,UUID actorId,int expected,Map<String,Object> body) {
        Map<String,Object> plan=lockedPlan(projectId,planId,actorId,"SUBMITTER","ADMIN");
        if(((Number)plan.get("version")).intValue()!=expected)throw conflict("计划版本已变更");
        validateBody(plan,body); UUID id=UUID.randomUUID(); String json=Json.write(body);
        data.plan(id,(UUID)plan.get("idea_revision_id"),(UUID)plan.get("planning_run_id"),data.nextPlanSequence((UUID)plan.get("idea_revision_id")),planId,json,Json.hash(json),actorId);
        return projectPlan(data.planContext(id));
    }
    @Transactional
    public Map<String,Object> confirm(UUID projectId,UUID planId,UUID actorId,int expected,String contentHash) {
        Map<String,Object> plan=lockedPlan(projectId,planId,actorId,"REVIEWER","ADMIN");
        if(!"DRAFT".equals(plan.get("status")) || ((Number)plan.get("version")).intValue()!=expected || !contentHash.equals(plan.get("content_hash")))throw conflict("计划内容或状态已变更，不能确认旧内容");
        Map<String,Object> latest=data.latestRevision((UUID)plan.get("idea_id"));
        if(!latest.get("id").equals(plan.get("idea_revision_id")))throw conflict("Idea 已有新修订，请先审查新修订计划");
        validateBody(plan,Json.object((String)plan.get("body_json")));
        data.supersede((UUID)plan.get("idea_id")); data.confirm(planId,actorId);
        return projectPlan(data.planContext(planId));
    }
    private Map<String,Object> lockedPlan(UUID projectId,UUID planId,UUID actorId,String... roles) {
        access.require(projectId,actorId,roles); Map<String,Object> context=require(data.planContext(planId));
        if(!projectId.equals(context.get("project_id")))throw new ApiProblem(404,"RESOURCE_NOT_FOUND","计划不属于当前项目");
        require(data.lockIdea(projectId,(UUID)context.get("idea_id"))); return require(data.lockPlan(planId));
    }
    private void validateBody(Map<String,Object> plan,Map<String,Object> body) {
        Map<String,Object> run=data.runById((UUID)plan.get("planning_run_id")), input=data.inputById((UUID)run.get("snapshot_id"));
        Map<String,Object> repository=repositories.load((UUID)plan.get("project_id"),(UUID)input.get("repository_snapshot_id"));
        validator.validate(body,Json.object((String)repository.get("body_json")));
        if(!"PLAN".equals(body.get("kind")))throw new ApiProblem(422,"PLAN_REQUIRED","计划版本必须包含实际 Issue 和验收条件");
    }
    private Map<String,Object> projectPlan(Map<String,Object> row) {
        Map<String,Object> result=new LinkedHashMap<>(row); result.put("body",Json.object((String)result.remove("body_json"))); return result;
    }
    public Map<String,Object> diff(UUID projectId,UUID ideaId,UUID actorId,UUID from,UUID to) {
        access.require(projectId,actorId); require(data.idea(projectId,ideaId));
        Map<String,Object> before=require(data.planContext(from)), after=require(data.planContext(to));
        if(!ideaId.equals(before.get("idea_id")) || !ideaId.equals(after.get("idea_id")))throw new ApiProblem(422,"PLAN_SCOPE_INVALID","比较的计划必须属于同一 Idea");
        Map<String,Object> oldBody=Json.object((String)before.get("body_json")), newBody=Json.object((String)after.get("body_json"));
        Map<String,Map<String,Object>> oldIssues=new LinkedHashMap<>(), newIssues=new LinkedHashMap<>();
        for(Map<String,Object> issue:PlanValidator.objects(oldBody,"issues",100))oldIssues.put((String)issue.get("key"),issue);
        for(Map<String,Object> issue:PlanValidator.objects(newBody,"issues",100))newIssues.put((String)issue.get("key"),issue);
        Set<String> added=new LinkedHashSet<>(newIssues.keySet()); added.removeAll(oldIssues.keySet());
        Set<String> removed=new LinkedHashSet<>(oldIssues.keySet()); removed.removeAll(newIssues.keySet());
        Set<String> changed=new LinkedHashSet<>();
        for(String key:newIssues.keySet())if(oldIssues.containsKey(key) && !oldIssues.get(key).equals(newIssues.get(key)))changed.add(key);
        Set<String> affected=new LinkedHashSet<>(); affected.addAll(added); affected.addAll(removed); affected.addAll(changed);
        List<Map<String,Object>> oldDependencies=PlanValidator.objects(oldBody,"dependencies",500), newDependencies=PlanValidator.objects(newBody,"dependencies",500);
        Set<Map<String,Object>> oldEdges=new HashSet<>(oldDependencies), newEdges=new HashSet<>(newDependencies);
        for(Map<String,Object> edge:oldEdges)if(!newEdges.contains(edge))affected.add((String)edge.get("consumer"));
        for(Map<String,Object> edge:newEdges)if(!oldEdges.contains(edge))affected.add((String)edge.get("consumer"));
        Deque<String> pending=new ArrayDeque<>(affected);
        while(!pending.isEmpty()) {
            String provider=pending.remove();
            for(Map<String,Object> edge:newDependencies)if(provider.equals(edge.get("provider")) && affected.add((String)edge.get("consumer")))pending.add((String)edge.get("consumer"));
        }
        return Map.of("fromPlanId",from,"toPlanId",to,"addedIssueKeys",added,"removedIssueKeys",removed,"changedIssueKeys",changed,
                "affectedIssueKeys",affected,"dependenciesChanged",!oldEdges.equals(newEdges));
    }
    private Map<String,Object> require(Map<String,Object> row) { if(row==null)throw new ApiProblem(404,"RESOURCE_NOT_FOUND","规划资源不存在"); return row; }
    private ApiProblem conflict(String message) { return new ApiProblem(409,"STATE_CONFLICT",message); }
}
