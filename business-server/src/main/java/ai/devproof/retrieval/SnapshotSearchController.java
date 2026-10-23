package ai.devproof.retrieval;

import ai.devproof.infrastructure.ApiInput;
import java.util.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class SnapshotSearchController {
    private final SnapshotSearchService search;
    public SnapshotSearchController(SnapshotSearchService search) { this.search=search; }
    @PostMapping("/api/v1/input-snapshots/{snapshot}/search")
    public SnapshotSearchStore.Result search(@PathVariable UUID snapshot,@RequestAttribute("actorId") UUID actor,@RequestBody Map<String,Object> input) {
        Query query=query(input); return search.search(snapshot,actor,query.text(),query.limit(),query.preferred(),null);
    }
    public record Query(String text,int limit,List<String> preferred) {}
    public static Query query(Map<String,Object> input) {
        if(!Set.of("query","limit","preferred_source_roles").containsAll(input.keySet()))throw ApiInput.invalid();
        String text=ApiInput.text(input,"query",1,2000); Object rawLimit=input.getOrDefault("limit",5);
        if(!(rawLimit instanceof Number number) || number.doubleValue()!=number.intValue() || number.intValue()<1 || number.intValue()>20)throw ApiInput.invalid();
        Object rawRoles=input.getOrDefault("preferred_source_roles",List.of());
        if(!(rawRoles instanceof List<?> roles) || roles.size()>8)throw ApiInput.invalid(); List<String> preferred=new ArrayList<>();
        for(Object role:roles) { if(!(role instanceof String value) || value.codePointCount(0,value.length())>255)throw ApiInput.invalid(); preferred.add(value); }
        return new Query(text,number.intValue(),List.copyOf(preferred));
    }
}
