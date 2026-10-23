package ai.devproof.infrastructure;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Content-addressed files and registry records; the caller owns the business transaction. */
@Component
public class JavaArtifacts {
    private final JdbcTemplate jdbc;
    private final Path root;
    public JavaArtifacts(JdbcTemplate jdbc,@Value("${BUSINESS_ARTIFACT_WRITE_ROOT:/artifacts/java}") String root) { this.jdbc=jdbc; this.root=Path.of(root).toAbsolutePath().normalize(); }
    public Map<String,Object> save(UUID project,String kind,String schema,String mediaType,byte[] bytes) {
        String hash=Json.hash(bytes);
        var existing=jdbc.queryForList("SELECT * FROM artifact_objects WHERE project_id=? AND kind=? AND content_hash=?",project,kind,hash);
        if(!existing.isEmpty())return existing.getFirst();
        Path temporary=null;
        try {
            Files.createDirectories(root); Path base=root.toRealPath(), directory=base.resolve(project.toString()).resolve(kind.toLowerCase(Locale.ROOT));
            Files.createDirectories(directory); directory=directory.toRealPath(); if(!directory.startsWith(base))throw new IOException("Artifact scope");
            Path file=directory.resolve(hash.substring(7));
            if(!Files.exists(file)) {
                temporary=Files.createTempFile(directory,"write-",".tmp"); Files.write(temporary,bytes);
                try { Files.move(temporary,file,StandardCopyOption.ATOMIC_MOVE); }
                catch(FileAlreadyExistsException ignored) { /* Identical content can be produced concurrently. */ }
                catch(AtomicMoveNotSupportedException e) { try { Files.move(temporary,file); } catch(FileAlreadyExistsException ignored) {} }
            }
            if(!Files.isRegularFile(file,LinkOption.NOFOLLOW_LINKS) || !Json.hash(Files.readAllBytes(file)).equals(hash))throw new IOException("Artifact hash");
            jdbc.update("INSERT INTO artifact_objects(id,project_id,kind,content_hash,byte_size,media_type,schema_version,storage_uri) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(project_id,kind,content_hash) DO NOTHING",
                UUID.randomUUID(),project,kind,hash,bytes.length,mediaType,schema,file.toString());
            return jdbc.queryForMap("SELECT * FROM artifact_objects WHERE project_id=? AND kind=? AND content_hash=?",project,kind,hash);
        } catch(IOException e) { throw new ApiProblem(503,"ARTIFACT_WRITE_FAILED","临时材料制品无法持久化"); }
        finally { if(temporary!=null)try { Files.deleteIfExists(temporary); } catch(IOException ignored) {} }
    }
}
