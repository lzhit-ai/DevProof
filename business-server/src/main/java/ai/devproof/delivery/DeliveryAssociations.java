package ai.devproof.delivery;

import ai.devproof.infrastructure.*;
import ai.devproof.project.ProjectAccess;
import ai.devproof.source.GitHubSourceClient;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class DeliveryAssociations {
    public record Selection(String kind,UUID id) {}
    private record Candidate(DeliveryAssociationStore.Target target,List<String> overlap) {}
    private record Preparation(Map<String,Object> primary,CommandStore.Result replay) {}
    private final DeliveryAssociationStore data;
    private final ProjectAccess access;
    private final BusinessOwnership owners;
    private final CommandStore commands;
    private final BusinessAudit audit;
    private final GitHubSourceClient github;
    private final JavaArtifacts artifacts;
    private final TransactionTemplate transactions;
    public DeliveryAssociations(DeliveryAssociationStore data,ProjectAccess access,BusinessOwnership owners,CommandStore commands,
            BusinessAudit audit,GitHubSourceClient github,JavaArtifacts artifacts,TransactionTemplate transactions) {
        this.data=data; this.access=access; this.owners=owners; this.commands=commands; this.audit=audit;
        this.github=github; this.artifacts=artifacts; this.transactions=transactions;
    }
    @Transactional public List<Map<String,Object>> links(UUID project,UUID item,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); data.item(project,item,false); return data.links(item);
    }
    @Transactional public List<Map<String,Object>> targets(UUID project,UUID item,UUID actor) {
        access.require(project,actor,"SUBMITTER","REVIEWER","ADMIN"); return data.targets(project,data.item(project,item,false));
    }
    @Transactional public CommandStore.Result confirm(UUID project,UUID itemId,UUID actor,CommandStore.Context command,Selection selection,String reason) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaDeliveryAssociations();
        var item=data.item(project,itemId,true);
        return commands.execute(command,201,()->{
            var target=data.target(project,item,selection.kind(),selection.id(),false);
            var link=data.upsert(itemId,target,"CONFIRMED","USER",1,UnicodeText.strip(reason),actor,null);
            if(link.changed()) {
                Map<String,Object> payload=new LinkedHashMap<>(); payload.put("deliveryItemId",itemId.toString());
                payload.put("pullRequestResourceId",target.pullRequest()==null?null:target.pullRequest().toString());
                payload.put("gitSnapshotId",target.gitSnapshot()==null?null:target.gitSnapshot().toString());
                audit.append(project,actor,"DeliveryChangeLink",link.id(),"DELIVERY_CHANGE_LINK_CONFIRMED",command.correlationId(),payload,null,null);
            }
            return data.links(itemId).stream().filter(row->link.id().equals(row.get("id"))).findFirst().orElseThrow();
        });
    }
    @Transactional public CommandStore.Result propose(UUID project,UUID itemId,UUID actor,CommandStore.Context command,List<Selection> selections) {
        access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaDeliveryAssociations();
        var item=data.item(project,itemId,true);
        return commands.execute(command,201,()->{
            var revision=data.latest((UUID)item.get("external_resource_id"));
            String text=item.get("external_key")+" "+item.get("title")+" "+(revision==null?"":revision.get("title"))+" "+(revision==null?"":revision.get("body"));
            Set<String> itemTokens=AssociationTokens.extract(text);
            List<DeliveryAssociationStore.Target> resolved=selections.stream().map(selection->data.target(project,item,selection.kind(),selection.id())).toList();
            Map<String,Object> source=new LinkedHashMap<>(); source.put("id",itemId.toString()); source.put("externalKey",item.get("external_key"));
            source.put("primaryResourceRevisionId",revision==null?null:revision.get("id").toString()); source.put("primaryContentHash",revision==null?null:revision.get("content_hash"));
            Map<String,Object> manifest=Map.of("schemaVersion","agent-change-link-candidate-v1","deliveryItem",source,"candidateTargets",resolved.stream().map(DeliveryAssociationStore.Target::manifest).toList());
            List<Candidate> candidates=new ArrayList<>(); int existing=0,noOverlap=0;
            for(var target:resolved) {
                if(data.exists(itemId,target)) { existing++; continue; }
                Set<String> overlap=new TreeSet<>(AssociationTokens.extract(target.text())); overlap.retainAll(itemTokens);
                if(overlap.isEmpty()) { noOverlap++; continue; }
                candidates.add(new Candidate(target,List.copyOf(overlap)));
            }
            UUID run=UUID.randomUUID(); var proposal=data.proposal(run,project,itemId,actor,manifest,resolved.size(),candidates.size());
            Set<UUID> created=new HashSet<>();
            for(var candidate:candidates) {
                var overlap=candidate.overlap();
                String reason="受控候选 Agent（"+AssociationTokens.VERSION+"）仅比较事项来源版本与用户选定目标的标题/元数据；共享标识符："
                    +String.join("、",overlap.subList(0,Math.min(8,overlap.size())))+"。此为待人工确认的关联，不证明交付完成。";
                var link=data.upsert(itemId,candidate.target(),"CANDIDATE","AGENT",AssociationTokens.confidence(overlap.size()),reason,actor,run);
                if(!link.changed())throw new ApiProblem(409,"ASSOCIATION_CHANGED","候选关联在保存期间已变化，请重新提交");
                created.add(link.id());
            }
            Map<String,Object> counts=Map.of("createdCandidateCount",created.size(),"skippedExistingCount",existing,"skippedNoOverlapCount",noOverlap);
            Map<String,Object> payload=new LinkedHashMap<>(counts); payload.put("deliveryItemId",itemId.toString()); payload.put("rulesVersion",AssociationTokens.VERSION);
            audit.append(project,actor,"AgentChangeProposalRun",run,"AGENT_DELIVERY_CHANGE_CANDIDATES_PROPOSED",command.correlationId(),payload,null,null);
            return Map.of("proposal_run",proposal,"links",data.links(itemId).stream().filter(link->created.contains(link.get("id"))).toList(),
                "created_candidate_count",created.size(),"skipped_existing_count",existing,"skipped_no_overlap_count",noOverlap);
        });
    }
    public CommandStore.Result discover(UUID project,UUID itemId,UUID actor,CommandStore.Context command) {
        var preparation=transactions.execute(status->{
            access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaDeliveryAssociations();
            var item=data.item(project,itemId,true); var replay=commands.replay(command);
            return new Preparation(replay==null?data.primaryIssue(item):Map.of(),replay);
        });
        if(preparation.replay()!=null)return preparation.replay();
        var primary=preparation.primary(); long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(90);
        // No business transaction is held during provider pagination.
        GitHubSourceClient.Timeline timeline;
        try {
            timeline=github.issueTimeline((String)primary.get("repository_slug"),(String)primary.get("api_base_url"),
                (String)primary.get("secret_ref"),(String)primary.get("external_key"),()->System.nanoTime()<deadline);
        } catch(ApiProblem error) {
            if("SOURCE_SYNC_LEASE_EXPIRED".equals(error.code))throw new ApiProblem(503,Thread.currentThread().isInterrupted()?"SOURCE_DISCOVERY_CANCELLED":"SOURCE_DISCOVERY_TIMEOUT","GitHub 关联发现未在执行预算内完成");
            throw error;
        }
        Map<String,Object> body=Map.of("schemaVersion","github-timeline-v1","connectionId",primary.get("connection_id").toString(),
            "issueResourceId",primary.get("issue_resource_id").toString(),"issueRevisionId",primary.get("issue_revision_id").toString(),
            "events",timeline.events(),"pageCount",timeline.pageCount(),"truncated",timeline.truncated());
        byte[] frozen=Json.canonical(body).getBytes(StandardCharsets.UTF_8);
        return transactions.execute(status->{
            access.require(project,actor,"SUBMITTER","ADMIN"); owners.requireJavaDeliveryAssociations();
            var currentItem=data.item(project,itemId,true);
            // A completed command remains replayable after the configured source changes.
            var replay=commands.replay(command); if(replay!=null)return replay;
            var current=data.primaryIssue(currentItem);
            if(!primary.equals(current))throw new ApiProblem(409,"INPUT_STALE","发现期间事项来源或连接配置已变化，请重新执行");
            return commands.execute(command,200,()->{
                int changed=0,skipped=0,excluded=0; List<String> ids=new ArrayList<>();
                for(var event:timeline.events()) {
                    String number=pullRequestNumber(event,(String)primary.get("repository_slug"));
                    if(number==null) {
                        if("cross-referenced".equals(event.get("event")) && event.get("source") instanceof Map<?,?> source && source.get("issue") instanceof Map<?,?> issue && issue.get("pull_request") instanceof Map<?,?>)excluded++;
                        continue;
                    }
                    UUID resource=data.pullRequest((UUID)primary.get("connection_id"),number);
                    if(resource==null) { skipped++; continue; }
                    var target=data.target(project,currentItem,"PULL_REQUEST",resource,false);
                    var link=data.upsert(itemId,target,"CONFIRMED","PLATFORM",1,"GitHub Issue 时间线记录该 PR 对此事项的交叉引用",actor,null);
                    if(link.changed()) { changed++; ids.add(link.id().toString()); }
                }
                var artifact=artifacts.save(project,"GITHUB_TIMELINE","github-timeline-v1","application/json",frozen);
                Map<String,Object> payload=new LinkedHashMap<>(); payload.put("changedCount",changed); payload.put("skippedCount",skipped);
                payload.put("timelineArtifactId",artifact.get("id").toString()); payload.put("timelineHash",artifact.get("content_hash"));
                payload.put("issueRevisionId",primary.get("issue_revision_id").toString()); payload.put("changedLinkIds",ids);
                payload.put("pageCount",timeline.pageCount()); payload.put("truncated",timeline.truncated());
                payload.put("excludedEventCount",excluded);
                audit.append(project,actor,"DeliveryItem",itemId,"DELIVERY_PLATFORM_LINKS_DISCOVERED",command.correlationId(),payload,null,null);
                return Map.of("changed_count",changed,"skipped_count",skipped,"excluded_event_count",excluded,"page_count",timeline.pageCount(),"truncated",timeline.truncated(),"input_hash",artifact.get("content_hash"));
            });
        });
    }
    private static String pullRequestNumber(Map<String,Object> event,String slug) {
        if(!"cross-referenced".equals(event.get("event")) || !(event.get("source") instanceof Map<?,?> source)
            || !(source.get("issue") instanceof Map<?,?> issue) || !(issue.get("pull_request") instanceof Map<?,?> pr)
            || !(issue.get("number") instanceof Integer || issue.get("number") instanceof Long))return null;
        long number=((Number)issue.get("number")).longValue(); if(number<=0 || !(pr.get("url") instanceof String raw))return null;
        try {
            URI url=URI.create(raw);
            if(!"https".equals(url.getScheme()) || !"api.github.com".equalsIgnoreCase(url.getHost()) || url.getUserInfo()!=null
                || (url.getPort()!=-1 && url.getPort()!=443) || url.getRawQuery()!=null || url.getRawFragment()!=null
                || !url.getRawPath().equalsIgnoreCase("/repos/"+slug+"/pulls/"+number))return null;
            return Long.toString(number);
        } catch(IllegalArgumentException e) { return null; }
    }
}
