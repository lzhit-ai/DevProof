package ai.devproof.infrastructure;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Reads registered artifacts under the configured volume; no remote URL or arbitrary file tools. */
@Component
public class ControlledArtifacts {
    private final Path root;
    public ControlledArtifacts(@Value("${ARTIFACT_ROOT:/artifacts}") String root) { this.root=Path.of(root).toAbsolutePath().normalize(); }
    public byte[] read(String location,long maxBytes,String expectedHash) {
        if(location==null || location.isBlank())throw unavailable();
        try {
            Path base=root.toRealPath(), file=Path.of(location).toRealPath();
            if(file.equals(base) || !file.startsWith(base) || !Files.isRegularFile(file))throw unavailable();
            try(var input=Files.newInputStream(file)) {
                if(maxBytes<1 || maxBytes>=Integer.MAX_VALUE)throw new IllegalArgumentException("Artifact limit out of range");
                byte[] raw=input.readNBytes((int)maxBytes+1);
                if(raw.length>maxBytes)throw new ApiProblem(409,"ARTIFACT_LIMIT_EXCEEDED","冻结制品超过配置的读取上限");
                if(expectedHash!=null && !Json.hash(raw).equals(expectedHash))throw new ApiProblem(409,"ARTIFACT_HASH_MISMATCH","冻结制品内容摘要不一致");
                return raw;
            }
        } catch(IOException|InvalidPathException e) { throw unavailable(); }
    }
    public String text(String location,long maxBytes,String expectedHash) {
        try { return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(read(location,maxBytes,expectedHash))).toString(); }
        catch(CharacterCodingException e) { throw new ApiProblem(409,"ARTIFACT_ENCODING_INVALID","冻结文本制品不是有效 UTF-8"); }
    }
    private ApiProblem unavailable() { return new ApiProblem(409,"ARTIFACT_UNAVAILABLE","冻结制品缺失或不属于配置的制品存储范围"); }
}
