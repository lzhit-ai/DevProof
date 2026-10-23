package ai.devproof.planning;

import ai.devproof.infrastructure.ApiProblem;
import java.util.*;
import org.springframework.stereotype.Component;

@Component
public class PlanValidator {
    public void validate(Map<String,Object> body, Map<String,Object> repository) {
        fields(body,"kind","summary","questions","issues","dependencies","risks");
        String kind=text(body,"kind",32); text(body,"summary",12000);
        strings(body,"risks",100);
        List<Map<String,Object>> questions=objects(body,"questions",30), issues=objects(body,"issues",100), dependencies=objects(body,"dependencies",500);
        if (!Set.of("PLAN","CLARIFICATION").contains(kind) || (kind.equals("PLAN") && (issues.isEmpty() || !questions.isEmpty()))
                || (kind.equals("CLARIFICATION") && (questions.isEmpty() || !issues.isEmpty() || !dependencies.isEmpty()))) throw invalid("澄清与计划内容不一致");
        Set<String> questionKeys=new HashSet<>();
        for (Map<String,Object> question:questions) {
            fields(question,"key","question","reason"); unique(questionKeys,text(question,"key",100)); text(question,"question",6000); text(question,"reason",6000);
        }
        Map<String,Map<String,Object>> issueByKey=new LinkedHashMap<>();
        Map<String,Set<String>> deliverables=new HashMap<>();
        for (Map<String,Object> issue:issues) {
            fields(issue,"key","title","goal","scope","acceptanceCriteria","reuseRefs","deliverables","assumptions");
            String key=text(issue,"key",100);
            if (issueByKey.putIfAbsent(key,issue)!=null) throw invalid("Issue key 重复");
            text(issue,"title",300); text(issue,"goal",8000); text(issue,"scope",12000); strings(issue,"assumptions",100);
            List<Map<String,Object>> criteria=objects(issue,"acceptanceCriteria",100);
            if (criteria.isEmpty()) throw invalid("Issue 缺少验收条件");
            Set<String> criterionKeys=new HashSet<>();
            for (Map<String,Object> criterion:criteria) {
                fields(criterion,"key","condition","verificationMethod","requiredEvidence");
                unique(criterionKeys,text(criterion,"key",100));
                if(text(criterion,"condition",6000).strip().length()<3)throw invalid("验收条件至少需要 3 个字符");
                text(criterion,"verificationMethod",6000);
                if (strings(criterion,"requiredEvidence",30).isEmpty()) throw invalid("验收项缺少所需证据");
            }
            Set<String> artifacts=new HashSet<>();
            List<Map<String,Object>> outputs=objects(issue,"deliverables",100);
            if (outputs.isEmpty()) throw invalid("Issue 缺少产物契约");
            for (Map<String,Object> output:outputs) {
                fields(output,"key","kind","description","version","availabilityCondition");
                unique(artifacts,text(output,"key",100));
                if (!Set.of("API","DATA","COMPONENT","DOCUMENT","OTHER").contains(text(output,"kind",32))) throw invalid("产物类型无效");
                text(output,"description",6000); text(output,"version",100); text(output,"availabilityCondition",6000);
            }
            deliverables.put(key,artifacts);
            for (Map<String,Object> reference:objects(issue,"reuseRefs",100)) validateReference(reference,repository);
        }
        Map<String,List<String>> graph=new HashMap<>();
        Map<String,Integer> incoming=new HashMap<>();
        for (String key:issueByKey.keySet()) { graph.put(key,new ArrayList<>()); incoming.put(key,0); }
        Set<String> edges=new HashSet<>();
        for (Map<String,Object> dependency:dependencies) {
            fields(dependency,"consumer","provider","deliverable","condition","reason");
            String consumer=text(dependency,"consumer",100), provider=text(dependency,"provider",100), artifact=text(dependency,"deliverable",100);
            if (!issueByKey.containsKey(consumer) || !issueByKey.containsKey(provider) || consumer.equals(provider)
                    || !deliverables.get(provider).contains(artifact)) throw invalid("依赖引用不存在的 Issue 或产物");
            text(dependency,"condition",6000); text(dependency,"reason",6000);
            unique(edges,consumer+"\u0000"+provider+"\u0000"+artifact);
            graph.get(provider).add(consumer); incoming.compute(consumer,(key,value)->value+1);
        }
        Deque<String> ready=new ArrayDeque<>();
        incoming.forEach((key,count)->{if(count==0)ready.add(key);});
        int visited=0;
        while (!ready.isEmpty()) { String key=ready.remove(); visited++; for(String child:graph.get(key)) if(incoming.compute(child,(k,value)->value-1)==0)ready.add(child); }
        if (visited!=issueByKey.size()) throw invalid("产物依赖存在循环");
    }
    public void validateReference(Map<String,Object> reference, Map<String,Object> repository) {
        fields(reference,"path","targetSha","startLine","endLine","reason");
        String path=text(reference,"path",2048), sha=text(reference,"targetSha",64); text(reference,"reason",6000);
        int start=integer(reference,"startLine"), end=integer(reference,"endLine");
        if (!sha.equals(repository.get("targetSha")) || start<1 || end<start) throw invalid("仓库引用的 SHA 或行范围无效");
        Map<String,Object> file=objects(repository,"files",10000).stream().filter(item->path.equals(item.get("path"))).findFirst()
                .orElseThrow(()->invalid("复用依据不属于已捕获仓库材料"));
        if (end>integer(file,"lineCount")) throw invalid("复用引用超出文件行数");
    }
    public static void fields(Map<String,Object> object, String... keys) {
        if (!object.keySet().equals(Set.of(keys))) throw invalid("字段缺失或包含未定义字段");
    }
    public static String text(Map<String,Object> object,String key,int max) {
        if (!(object.get(key) instanceof String value) || value.isBlank() || value.length()>max) throw invalid("文本字段无效: "+key);
        return value;
    }
    public static int integer(Map<String,Object> object,String key) {
        if (!(object.get(key) instanceof Number value) || value.doubleValue()!=value.intValue()) throw invalid("整数字段无效: "+key); return value.intValue();
    }
    @SuppressWarnings("unchecked") public static List<Map<String,Object>> objects(Map<String,Object> object,String key,int max) {
        if (!(object.get(key) instanceof List<?> list) || list.size()>max || list.stream().anyMatch(item->!(item instanceof Map<?,?>))) throw invalid("对象列表无效: "+key);
        return (List<Map<String,Object>>)(List<?>)list;
    }
    public static List<String> strings(Map<String,Object> object,String key,int max) {
        if (!(object.get(key) instanceof List<?> list) || list.size()>max || list.stream().anyMatch(item->!(item instanceof String value) || value.isBlank() || value.length()>6000)) throw invalid("文本列表无效: "+key);
        return list.stream().map(item->(String)item).toList();
    }
    private static void unique(Set<String> seen,String key) { if(!seen.add(key)) throw invalid("存在重复标识或依赖"); }
    private static ApiProblem invalid(String message) { return new ApiProblem(422,"PLANNING_RESULT_INVALID",message); }
}
