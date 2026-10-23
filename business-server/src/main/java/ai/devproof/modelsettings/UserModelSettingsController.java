package ai.devproof.modelsettings;

import ai.devproof.infrastructure.ApiInput;
import java.util.*;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/me/ai-settings")
public class UserModelSettingsController {
    private final UserModelSettings settings;
    public UserModelSettingsController(UserModelSettings settings) { this.settings=settings; }
    @GetMapping public ResponseEntity<?> get(@RequestAttribute("actorId") UUID user) { return response(settings.get(user)); }
    @PutMapping public ResponseEntity<?> save(@RequestAttribute("actorId") UUID user,@RequestBody byte[] raw) { return response(settings.save(user,body(raw))); }
    @DeleteMapping public ResponseEntity<?> clear(@RequestAttribute("actorId") UUID user,@RequestBody byte[] raw) { return response(settings.clear(user,body(raw))); }
    private Map<String,Object> body(byte[] raw) { if(raw.length>16384)throw ApiInput.invalid(); return ApiInput.object(raw); }
    private ResponseEntity<?> response(Object value) { return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(value); }
}
