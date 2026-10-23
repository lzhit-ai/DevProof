package ai.devproof.project;

import ai.devproof.infrastructure.ApiProblem;
import java.util.Set;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import org.springframework.stereotype.Service;

@Service
public class ProjectAccess {
    @Mapper public interface Members {
        @Select("SELECT m.role FROM project_members m JOIN projects p ON p.id=m.project_id JOIN users u ON u.id=m.user_id AND u.status='ACTIVE' WHERE m.project_id=#{projectId} AND m.user_id=#{actorId} AND p.deleted_at IS NULL FOR SHARE OF p")
        String role(UUID projectId, UUID actorId);
    }
    private final Members members;
    public ProjectAccess(Members members) { this.members = members; }
    public String role(UUID projectId,UUID actorId) {
        String role=members.role(projectId,actorId);
        if(role==null)throw new ApiProblem(403,"AUTH_FORBIDDEN","当前用户没有该项目资源权限"); return role;
    }
    public void require(UUID projectId, UUID actorId, String... roles) {
        String role = role(projectId, actorId);
        if (role == null || (roles.length > 0 && !Set.of(roles).contains(role))) throw new ApiProblem(403, "AUTH_FORBIDDEN", "当前用户没有该项目资源权限");
    }
}
