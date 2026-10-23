package ai.devproof.verification;

import ai.devproof.agentjob.AgentTaskTool;
import ai.devproof.infrastructure.*;
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class RegisteredHttpTool implements AgentTaskTool {
    private final VerificationToolScope scope;
    private final VerificationToolStore store;
    private final ToolEndpointPolicy policy;
    public RegisteredHttpTool(VerificationToolScope scope,VerificationToolStore store,ToolEndpointPolicy policy) {
        this.scope=scope; this.store=store; this.policy=policy;
    }
    public String key() { return "query_registered_tool"; }
    public String version() { return "v1"; }
    public Object execute(Map<String,Object> payload,Map<String,Object> arguments) {
        if(!arguments.keySet().equals(Set.of("capabilityKey","toolKey")) || !(arguments.get("capabilityKey") instanceof String capability) || !(arguments.get("toolKey") instanceof String key))throw invalid();
        Map<String,Object> run=scope.require(payload), node=scope.nodes((UUID)run.get("id")).stream().filter(item->Boolean.TRUE.equals(item.get("enabled")) && capability.equals(item.get("capabilityKey")) && !VerificationOrchestration.BUILT_IN.contains(capability)).findFirst().orElseThrow(this::invalid);
        Map<String,Object> registered=VerificationMaterials.objects(node.get("tools")).stream().filter(item->key.equals(item.get("key")) && "HTTP_QUERY".equals(item.get("type"))).findFirst().orElseThrow(this::invalid);
        Map<String,Object> previous=store.tool(payload,capability,key); if(previous!=null)return previous;
        URI uri;
        try { uri=URI.create(policy.endpoint((String)registered.get("endpointUrl"))); }
        catch(RuntimeException e) { throw invalid(); }
        if(registered.get("secretRef")!=null && !(registered.get("secretRef") instanceof String))throw invalid();
        String secret=policy.secret((String)registered.get("secretRef"));
        String query="analysisRunId="+run.get("id")+"&inputSnapshotId="+run.get("snapshot_id")+"&capabilityKey="+URLEncoder.encode(capability,StandardCharsets.UTF_8);
        HttpURLConnection connection=null;
        try {
            connection=(HttpURLConnection)URI.create(uri.toASCIIString()+"?"+query).toURL().openConnection();
            connection.setInstanceFollowRedirects(false); connection.setRequestMethod("GET");
            int timeout=scope.limit(payload,"toolTimeoutSeconds")*1000;
            connection.setConnectTimeout(timeout); connection.setReadTimeout(timeout);
            connection.setRequestProperty("Accept","application/json, text/plain;q=0.9"); connection.setRequestProperty("User-Agent","DevProof-AgentTool/2.0");
            if(secret!=null)connection.setRequestProperty("Authorization","Bearer "+secret);
            int status=connection.getResponseCode(); if(status<200 || status>=300)throw new ApiProblem(503,"TOOL_UNAVAILABLE","工具返回 HTTP "+status);
            String media=Objects.toString(connection.getContentType(),"").split(";",2)[0].trim().toLowerCase(Locale.ROOT);
            if(!Set.of("application/json","text/plain").contains(media))throw new ApiProblem(422,"TOOL_RESPONSE_INVALID","工具仅允许返回 JSON 或纯文本");
            int limit=scope.limit(payload,"toolResponseLimitBytes"); byte[] bytes;
            long deadline=System.nanoTime()+java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(timeout);
            try(var input=connection.getInputStream();var output=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[8192]; int count;
                while((count=input.read(buffer,0,Math.min(buffer.length,limit+1-output.size())))!=-1) {
                    if(System.nanoTime()>=deadline)throw new SocketTimeoutException();
                    output.write(buffer,0,count); if(output.size()>limit)break;
                }
                bytes=output.toByteArray();
            }
            if(bytes.length>limit)throw new ApiProblem(422,"TOOL_RESPONSE_TOO_LARGE","工具响应超过冻结预算");
            String text=StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
            if(media.equals("application/json"))try { Json.read(text); } catch(RuntimeException e) { throw new ApiProblem(422,"TOOL_RESPONSE_INVALID","工具响应不是有效 JSON"); }
            return store.recordTool(payload,capability,key,bytes,media,Map.of("toolKey",key,"host",uri.getHost(),"responseType",media,"statusCode",status));
        } catch(CharacterCodingException e) { throw new ApiProblem(422,"TOOL_RESPONSE_INVALID","工具响应不是 UTF-8"); }
        catch(IOException e) { throw new ApiProblem(503,"TOOL_UNAVAILABLE","工具连接失败或读取超时"); }
        finally { if(connection!=null)connection.disconnect(); }
    }
    private ApiProblem invalid() { return new ApiProblem(422,"TOOL_CONFIG_INVALID","工具不属于冻结自定义能力或端点不在 HTTPS 白名单"); }
}
