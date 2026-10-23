package ai.devproof.verification;

import ai.devproof.infrastructure.*;
import java.net.URI;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Registration and execution share the same server-owned endpoint and secret-reference policy. */
@Component
public class ToolEndpointPolicy {
    private final Set<String> hosts,secrets;
    public ToolEndpointPolicy(@Value("${AGENT_TOOL_ALLOWED_HOSTS:}") String hosts,@Value("${AGENT_TOOL_SECRET_REFS:}") String secrets) {
        this.hosts=parse(hosts,true); this.secrets=parse(secrets,false);
    }
    public String endpoint(String value) {
        String text=UnicodeText.strip(value); URI uri;
        try { uri=URI.create(text); } catch(RuntimeException e) { throw invalid(); }
        if(!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null || uri.getQuery()!=null || uri.getFragment()!=null
            || uri.getPort()!=-1 && uri.getPort()!=443)throw invalid();
        if(!hosts.contains(uri.getHost().toLowerCase(Locale.ROOT)))throw new ApiProblem(403,"AUTH_FORBIDDEN","HTTP 查询端点必须先由服务端 AGENT_TOOL_ALLOWED_HOSTS 授权");
        return text;
    }
    public void reference(String ref,boolean http) {
        if(ref==null || ref.isEmpty())return;
        if(!ref.matches("[A-Z][A-Z0-9_]{2,159}"))throw new ApiProblem(422,"INPUT_INVALID","密钥引用只能是服务端大写环境变量名");
        if(http && !secrets.contains(ref))throw new ApiProblem(403,"TOOL_SECRET_FORBIDDEN","工具密钥引用尚未由服务端授权");
    }
    public String secret(String ref) {
        if(ref==null || ref.isEmpty())return null;
        reference(ref,true); String value=System.getenv(ref);
        if(value==null || value.isBlank())throw new ApiProblem(503,"TOOL_SECRET_UNAVAILABLE","服务端尚未配置工具密钥"); return value;
    }
    private static Set<String> parse(String value,boolean lower) {
        String clean=value.trim();
        if(clean.startsWith("["))try { Object parsed=Json.read(clean); if(parsed instanceof List<?> list)return new HashSet<>(list.stream().map(item->lower?item.toString().trim().toLowerCase(Locale.ROOT):item.toString().trim()).toList()); } catch(RuntimeException ignored) {}
        Set<String> result=new HashSet<>(); for(String item:value.split(","))if(!item.isBlank())result.add(lower?item.trim().toLowerCase(Locale.ROOT):item.trim()); return result;
    }
    private ApiProblem invalid() { return new ApiProblem(422,"INPUT_INVALID","HTTP 查询工具仅支持无凭据、无查询串且端口为 443 的 HTTPS 地址"); }
}
