package ai.devproof.auth;

import ai.devproof.infrastructure.ApiProblem;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {
    private final UserMapper users;
    private final TokenService tokens;
    private final RegistrationService registrations;
    public AuthController(UserMapper users, TokenService tokens,RegistrationService registrations) { this.users = users; this.tokens = tokens; this.registrations=registrations; }
    public record Login(@NotBlank @Size(max=255) String email, @NotNull @Size(min=8, max=200) String password) {}
    public record Registration(String display_name,String email,String password) {}

    @PostMapping("/register")
    @ResponseStatus(org.springframework.http.HttpStatus.CREATED)
    public Map<String,Object> register(@RequestBody Registration input) { return registrations.register(input.display_name(),input.email(),input.password()); }

    @PostMapping("/login")
    public Map<String, Object> login(@Valid @RequestBody Login input) {
        Map<String, Object> user = users.byEmail(input.email());
        if (user == null || !"ACTIVE".equals(user.get("status")) || !tokens.verifyPassword(input.password(), (String) user.get("password_hash")))
            throw new ApiProblem(401, "AUTH_INVALID", "邮箱或密码错误");
        return Map.of("access_token", tokens.issue((UUID) user.get("id")), "token_type", "bearer");
    }

    @GetMapping("/me")
    public Map<String, Object> me(@RequestAttribute("actorId") UUID actorId) {
        Map<String, Object> user = users.byId(actorId);
        return Map.of("id", user.get("id"), "email", user.get("email"), "display_name", user.get("display_name"));
    }
}
