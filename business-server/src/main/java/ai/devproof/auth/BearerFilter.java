package ai.devproof.auth;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.Json;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class BearerFilter extends OncePerRequestFilter {
    private final TokenService tokens;
    private final UserMapper users;
    public BearerFilter(TokenService tokens, UserMapper users) { this.tokens = tokens; this.users = users; }
    @Override protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getRequestURI().startsWith("/internal/") || request.getRequestURI().startsWith("/api/v1/health/")
                || request.getRequestURI().equals("/api/v1/auth/login") || request.getRequestURI().equals("/api/v1/auth/register");
    }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain) throws ServletException, IOException {
        try {
            String header = request.getHeader("Authorization");
            if (header == null || !header.startsWith("Bearer ")) throw new ApiProblem(401, "AUTH_REQUIRED", "缺少 Bearer Token");
            UUID actorId = tokens.decode(header.substring(7));
            Map<String, Object> user = users.byId(actorId);
            if (user == null || !"ACTIVE".equals(user.get("status"))) throw new ApiProblem(401, "AUTH_INVALID", "用户不可用");
            request.setAttribute("actorId", actorId);
            SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(actorId, null, List.of()));
        } catch (ApiProblem e) {
            response.setStatus(e.status); response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(Json.write(Json.error(e.code, e.getMessage(), request.getHeader("X-Correlation-Id"))));
            return;
        } catch (org.springframework.dao.DataAccessException e) {
            response.setStatus(503); response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write(Json.write(Json.error("DATABASE_UNAVAILABLE", "业务数据库当前不可用", request.getHeader("X-Correlation-Id"))));
            return;
        }
        chain.doFilter(request, response);
    }
}
