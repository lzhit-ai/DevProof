package ai.devproof.modelsettings;

import ai.devproof.infrastructure.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.Timestamp;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserModelSettings {
    private final JdbcTemplate jdbc;
    private final ModelKeyCipher cipher;
    private final Map<String,Object> defaults;
    private final Set<String> hosts=new HashSet<>();
    public record Binding(String reference,Map<String,Object> configuration) {}
    public UserModelSettings(JdbcTemplate jdbc,ModelKeyCipher cipher,
            @Value("${GENERATION_PROVIDER:deepseek}") String provider,@Value("${GENERATION_MODEL:deepseek-v4-flash}") String model,
            @Value("${GENERATION_BASE_URL:https://api.deepseek.com}") String baseUrl,
            @Value("${USER_MODEL_ALLOWED_HOSTS:api.deepseek.com,api.openai.com,openrouter.ai,dashscope.aliyuncs.com,api.moonshot.cn,api.siliconflow.cn,open.bigmodel.cn}") String allowedHosts) {
        this.jdbc=jdbc; this.cipher=cipher;
        defaults=Map.of("provider",provider,"model",model,"baseUrl",baseUrl.replaceAll("/+$",""));
        for(String host:allowedHosts.split(","))if(!host.isBlank())hosts.add(host.trim().toLowerCase(Locale.ROOT));
        try { String host=URI.create(baseUrl).getHost(); if(host!=null)hosts.add(host.toLowerCase(Locale.ROOT)); } catch(IllegalArgumentException ignored) {}
    }
    public Map<String,Object> get(UUID user) { return view(row(user,false)); }
    @Transactional public Map<String,Object> save(UUID user,Map<String,Object> body) {
        if(!Set.of("modelId","apiKey","expectedVersion").containsAll(body.keySet()))throw ApiInput.invalid();
        String id=ApiInput.text(body,"modelId",1,128);
        ModelCatalog.Model selected=ModelCatalog.MODELS.stream().filter(item->item.id().equals(id)).findFirst()
            .orElseThrow(()->new ApiProblem(422,"MODEL_UNKNOWN","请选择列表中的模型"));
        String provider=selected.provider(),model=selected.model(),base=endpoint(selected.baseUrl());
        String supplied=ApiInput.optionalText(body,"apiKey",8192);
        if(supplied!=null && supplied.chars().anyMatch(value->Character.isISOControl(value) || Character.isWhitespace(value)))throw new ApiProblem(422,"INPUT_INVALID","API Key 不能包含空白或控制字符");
        lock(user); Map<String,Object> current=row(user,true); expectVersion(body,current);
        if((supplied==null || supplied.isEmpty()) && current!=null
                && (!provider.equals(current.get("provider")) || !base.equals(current.get("base_url"))))
            throw new ApiProblem(422,"MODEL_KEY_REQUIRED","切换服务商后，请填写对应服务商的 API Key");
        String old=current==null?null:cipher.decrypt(user,(UUID)current.get("credential_id"),(String)current.get("encrypted_api_key"));
        String secret=supplied==null || supplied.isEmpty()?old:supplied;
        if(secret==null || secret.isBlank())throw new ApiProblem(422,"MODEL_KEY_REQUIRED","请填写 API Key");
        if(current!=null && provider.equals(current.get("provider")) && model.equals(current.get("model")) && base.equals(current.get("base_url"))
                && MessageDigest.isEqual(secret.getBytes(StandardCharsets.UTF_8),old.getBytes(StandardCharsets.UTF_8)))return view(current);
        UUID credential=UUID.randomUUID(); String encrypted=cipher.encrypt(user,credential,secret);
        jdbc.update("""
            INSERT INTO user_model_settings(user_id,credential_id,provider,model,base_url,encrypted_api_key)
            VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET credential_id=EXCLUDED.credential_id,
              provider=EXCLUDED.provider,model=EXCLUDED.model,base_url=EXCLUDED.base_url,encrypted_api_key=EXCLUDED.encrypted_api_key,
              version=user_model_settings.version+1,updated_at=clock_timestamp()
            """,user,credential,provider,model,base,encrypted);
        return view(row(user,false));
    }
    @Transactional public Map<String,Object> clear(UUID user,Map<String,Object> body) {
        if(!body.keySet().equals(Set.of("expectedVersion")))throw ApiInput.invalid();
        lock(user); Map<String,Object> current=row(user,true); expectVersion(body,current);
        jdbc.update("DELETE FROM user_model_settings WHERE user_id=?",user); return view(null);
    }
    @Transactional public Binding freeze(UUID user) {
        // This row lock keeps configuration changes out of a task's enqueue transaction.
        var rows=jdbc.queryForList("SELECT * FROM user_model_settings WHERE user_id=? FOR SHARE",user);
        if(rows.isEmpty())throw new ApiProblem(409,"USER_MODEL_NOT_CONFIGURED","请先在设置中保存你的个人 AI 配置");
        Map<String,Object> row=rows.getFirst(); return new Binding("user-model:"+row.get("credential_id"),configuration(row));
    }
    public Map<String,Object> runtimeCredential(UUID user,String reference,Map<String,Object> frozen) {
        Map<String,Object> row=row(user,false);
        if(row==null)throw new ApiProblem(409,"USER_MODEL_NOT_CONFIGURED","任务发起用户尚未配置个人 AI 模型");
        if(!("user-model:"+row.get("credential_id")).equals(reference) || !configuration(row).equals(frozen))
            throw new ApiProblem(409,"MODEL_CONFIG_CHANGED","个人 AI 配置已变更，请重新创建任务");
        endpoint((String)row.get("base_url"));
        return Map.of("modelConfigRef",reference,"modelConfiguration",frozen,"apiKey",cipher.decrypt(user,(UUID)row.get("credential_id"),(String)row.get("encrypted_api_key")));
    }
    private Map<String,Object> row(UUID user,boolean locked) {
        var rows=jdbc.queryForList("SELECT * FROM user_model_settings WHERE user_id=?"+(locked?" FOR UPDATE":""),user);
        return rows.isEmpty()?null:rows.getFirst();
    }
    private Map<String,Object> configuration(Map<String,Object> row) { return Map.of("provider",row.get("provider"),"model",row.get("model"),"baseUrl",row.get("base_url")); }
    private Map<String,Object> view(Map<String,Object> row) {
        Map<String,Object> result=new LinkedHashMap<>(); result.put("configured",row!=null); result.put("version",row==null?0:row.get("version"));
        var models=ModelCatalog.MODELS.stream().filter(item->hosts.contains(URI.create(item.baseUrl()).getHost())).toList();
        Map<String,Object> configuration=row==null?defaults:configuration(row);
        String selected=ModelCatalog.selectedId(configuration);
        String matched=selected;
        if(row==null && models.stream().noneMatch(item->item.id().equals(matched)))
            selected=models.isEmpty()?null:models.getFirst().id();
        result.put("configuration",configuration); result.put("models",models); result.put("selectedModelId",selected);
        result.put("updatedAt",row==null?null:((Timestamp)row.get("updated_at")).toInstant().toString()); return result;
    }
    private void lock(UUID user) { jdbc.queryForObject("SELECT pg_advisory_xact_lock(hashtextextended(CAST(? AS text),2084))",Object.class,user.toString()); }
    private void expectVersion(Map<String,Object> body,Map<String,Object> current) {
        if(!(body.get("expectedVersion") instanceof Number version) || version.doubleValue()!=version.longValue() || version.longValue()<0)throw ApiInput.invalid();
        long actual=current==null?0:((Number)current.get("version")).longValue();
        if(version.longValue()!=actual)throw new ApiProblem(409,"VERSION_CONFLICT","个人 AI 配置已更新，请刷新后重试");
    }
    private String endpoint(String value) {
        String text=value.trim().replaceAll("/+$",""); URI uri;
        try { uri=URI.create(text); } catch(IllegalArgumentException e) { throw ApiInput.invalid(); }
        if(!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost()==null || uri.getUserInfo()!=null || uri.getQuery()!=null || uri.getFragment()!=null
                || uri.getPort()!=-1 && uri.getPort()!=443)throw new ApiProblem(422,"MODEL_ENDPOINT_INVALID","模型服务地址需使用无凭据和查询参数的 HTTPS 地址");
        if(!hosts.contains(uri.getHost().toLowerCase(Locale.ROOT)))throw new ApiProblem(422,"MODEL_ENDPOINT_NOT_ALLOWED","该模型服务地址尚未获服务器授权，请联系管理员添加");
        return text;
    }
}
