package ai.devproof.modelsettings;

import java.util.*;

/** Official Chat Completions models supported by the task worker. */
public final class ModelCatalog {
    private ModelCatalog() {}
    public record Model(String id,String label,String provider,String providerLabel,String model,String baseUrl) {}

    // Provider documentation checked on 2026-10-23. These are API IDs, not display names.
    public static final List<Model> MODELS=List.of(
        new Model("deepseek/flash","DeepSeek Flash","deepseek","DeepSeek","deepseek-flash","https://api.deepseek.com"),
        new Model("deepseek/pro","DeepSeek V4 Pro","deepseek","DeepSeek","deepseek-v4-pro","https://api.deepseek.com"),
        new Model("dashscope/plus","通义千问 Plus","dashscope","阿里云百炼（北京）","qwen-plus","https://dashscope.aliyuncs.com/compatible-mode/v1"),
        new Model("dashscope/flash","通义千问 Flash","dashscope","阿里云百炼（北京）","qwen-flash","https://dashscope.aliyuncs.com/compatible-mode/v1"),
        new Model("moonshot/k2.6","Kimi K2.6","moonshot","月之暗面","kimi-k2.6","https://api.moonshot.cn/v1"),
        new Model("zhipu/4.7","GLM-4.7","zhipu","智谱","glm-4.7","https://open.bigmodel.cn/api/paas/v4"),
        new Model("openai/4.1","GPT-4.1","openai","OpenAI","gpt-4.1","https://api.openai.com/v1"),
        new Model("openai/4.1-mini","GPT-4.1 mini","openai","OpenAI","gpt-4.1-mini","https://api.openai.com/v1")
    );

    public static String selectedId(Map<String,Object> configuration) {
        String model=(String)configuration.get("model");
        if("deepseek-v4-flash".equals(model) || "deepseek-v4-flash-vision-exp".equals(model))model="deepseek-flash";
        String apiModel=model;
        return MODELS.stream().filter(item->item.provider().equals(configuration.get("provider"))
                && item.model().equals(apiModel) && item.baseUrl().equals(configuration.get("baseUrl")))
            .map(Model::id).findFirst().orElse(null);
    }
}
