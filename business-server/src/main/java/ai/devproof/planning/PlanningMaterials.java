package ai.devproof.planning;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class PlanningMaterials {
    private final PlanningMapper data;
    private final RepositorySnapshotService repositories;
    public PlanningMaterials(PlanningMapper data,RepositorySnapshotService repositories) { this.data=data; this.repositories=repositories; }
    public Object execute(String key,Map<String,Object> payload,Map<String,Object> arguments) {
        UUID projectId=UUID.fromString((String)payload.get("projectId"));
        @SuppressWarnings("unchecked") Map<String,Object> ref=(Map<String,Object>)payload.get("inputSnapshotRef");
        if(!"PLANNING".equals(ref.get("kind")))throw new ApiProblem(403,"TOOL_FORBIDDEN","该工具只接受规划输入");
        Map<String,Object> row=data.inputById(UUID.fromString((String)ref.get("id")));
        if(row==null || !projectId.equals(row.get("project_id")) || !ref.get("contentHash").equals(row.get("content_hash"))
                || !Json.hash((String)row.get("input_json")).equals(row.get("content_hash")))throw new ApiProblem(409,"INPUT_STALE","规划输入引用无效");
        Map<String,Object> input=Json.object((String)row.get("input_json"));
        Map<String,Object> repositoryRow=repositories.load(projectId,(UUID)row.get("repository_snapshot_id"));
        Map<String,Object> repository=Json.object((String)repositoryRow.get("body_json"));
        @SuppressWarnings("unchecked") Map<String,Object> frozenRepoRef=(Map<String,Object>)input.get("repositorySnapshot");
        if(!frozenRepoRef.get("contentHash").equals(repositoryRow.get("content_hash")))throw new ApiProblem(409,"INPUT_STALE","规划仓库快照摘要不一致");
        List<Map<String,Object>> files=PlanValidator.objects(repository,"files",10000);
        if(key.equals("read_snapshot")) {
            PlanValidator.fields(arguments);
            Map<String,Object> result=new LinkedHashMap<>(input);
            result.put("files",files.stream().map(file->Map.of("path",file.get("path"),"lineCount",file.get("lineCount"),"contentHash",file.get("contentHash"))).toList());
            result.put("coverage",repository.get("coverage")); result.put("evidenceRole","CONTEXT_ONLY"); return result;
        }
        if(key.equals("read_file")) {
            PlanValidator.fields(arguments,"path","startLine","endLine");
            String path=PlanValidator.text(arguments,"path",2048); int start=PlanValidator.integer(arguments,"startLine"), end=PlanValidator.integer(arguments,"endLine");
            Map<String,Object> file=files.stream().filter(item->path.equals(item.get("path"))).findFirst()
                    .orElseThrow(()->new ApiProblem(404,"SNAPSHOT_FILE_NOT_FOUND","文件不在任务捕获的仓库范围"));
            String[] lines=((String)file.get("content")).split("\n",-1);
            if(start<1 || start>lines.length || end<start || (long)end-start>=200)
                throw new ApiProblem(422,"TOOL_INPUT_INVALID","文件共 "+lines.length+" 行；起始行必须位于文件内，每次请求至多 200 行");
            end=Math.min(end,lines.length);
            String content=String.join("\n",Arrays.copyOfRange(lines,start-1,end));
            return Map.of("path",path,"targetSha",repository.get("targetSha"),"startLine",start,"endLine",end,
                    "lineCount",lines.length,"content",content.length()>24000?content.substring(0,24000):content,"truncated",content.length()>24000,"evidenceRole","CONTEXT_ONLY");
        }
        if(key.equals("search_snapshot")) {
            PlanValidator.fields(arguments,"query"); String query=PlanValidator.text(arguments,"query",200).toLowerCase(Locale.ROOT);
            List<Map<String,Object>> matches=new ArrayList<>(); boolean limited=false;
            outer: for(Map<String,Object> file:files) {
                String[] lines=((String)file.get("content")).split("\n",-1);
                for(int line=0;line<lines.length;line++)if(lines[line].toLowerCase(Locale.ROOT).contains(query)) {
                    if(matches.size()==20){limited=true;break outer;}
                    int start=Math.max(0,line-2),end=Math.min(lines.length,line+3); String snippet=String.join("\n",Arrays.copyOfRange(lines,start,end));
                    matches.add(Map.of("path",file.get("path"),"targetSha",repository.get("targetSha"),"startLine",start+1,"endLine",end,
                            "content",snippet.length()>4000?snippet.substring(0,4000):snippet,"truncated",snippet.length()>4000));
                }
            }
            return Map.of("matches",matches,"limitReached",limited,"evidenceRole","CONTEXT_ONLY");
        }
        throw new ApiProblem(404,"TOOL_NOT_FOUND","规划工具不存在");
    }
}
