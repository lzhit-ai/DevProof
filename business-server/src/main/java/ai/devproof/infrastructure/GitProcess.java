package ai.devproof.infrastructure;

import java.io.*;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

/** Runs a fixed Git command with bounded output and an explicitly supplied environment. */
public final class GitProcess {
    private GitProcess() {}
    public static Map<String,String> localEnvironment() {
        Map<String,String> values=new HashMap<>();
        for(String key:List.of("PATH","SystemRoot","WINDIR","TEMP","TMP"))if(System.getenv(key)!=null)values.put(key,System.getenv(key));
        values.put("GIT_TERMINAL_PROMPT","0"); values.put("GIT_CONFIG_NOSYSTEM","1"); values.put("GIT_NO_REPLACE_OBJECTS","1");
        values.put("GIT_CONFIG_GLOBAL",System.getProperty("os.name").startsWith("Windows")?"NUL":"/dev/null");
        return values;
    }
    public static byte[] run(Path bare,Map<String,String> environment,long deadline,int limit,String... arguments) throws IOException {
        List<String> command=new ArrayList<>(List.of("git","-c","core.hooksPath=/dev/null","-c","credential.helper=","-c","http.followRedirects=false","-c","protocol.file.allow=never","-c","protocol.ext.allow=never"));
        if(bare!=null)command.add("--git-dir="+bare);
        command.addAll(Arrays.asList(arguments));
        ProcessBuilder builder=new ProcessBuilder(command).redirectError(ProcessBuilder.Redirect.DISCARD);
        builder.environment().clear(); builder.environment().putAll(environment);
        Process process=builder.start(); ByteArrayOutputStream output=new ByteArrayOutputStream(); AtomicReference<RuntimeException> error=new AtomicReference<>();
        Thread reader=Thread.startVirtualThread(()-> {
            try(var input=process.getInputStream()) {
                byte[] buffer=new byte[8192]; int count;
                while((count=input.read(buffer))!=-1) {
                    if(output.size()+count>limit) { error.set(new ApiProblem(409,"GIT_READ_BUDGET_EXCEEDED","Git 输出超过授权读取预算")); process.destroyForcibly(); break; }
                    output.write(buffer,0,count);
                }
            } catch(IOException e) { error.compareAndSet(null,new ApiProblem(503,"GIT_READ_FAILED","Git 输出读取失败")); }
        });
        try {
            long remaining=deadline-System.nanoTime();
            if(remaining<=0 || !process.waitFor(remaining,TimeUnit.NANOSECONDS)) { process.destroyForcibly(); throw new ApiProblem(503,"GIT_TIMEOUT","仓库读取超时"); }
            reader.join(2000);
            if(reader.isAlive())throw new ApiProblem(503,"GIT_READ_TIMEOUT","Git 输出尚未完整读取");
            if(error.get()!=null)throw error.get();
            if(process.exitValue()!=0)throw new ApiProblem(503,"GIT_UNAVAILABLE","冻结提交或文件当前不可读取");
            return output.toByteArray();
        } catch(InterruptedException e) { Thread.currentThread().interrupt(); process.destroyForcibly(); throw new ApiProblem(503,"GIT_INTERRUPTED","仓库读取已中断"); }
    }
}
