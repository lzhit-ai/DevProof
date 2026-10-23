package ai.devproof.auth;

import ai.devproof.infrastructure.ApiProblem;
import ai.devproof.infrastructure.DevProofProperties;
import ai.devproof.infrastructure.Json;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;
import javax.crypto.Mac;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Service;

@Service
public class TokenService {
    private static final Base64.Encoder ENCODER = Base64.getUrlEncoder().withoutPadding();
    private final DevProofProperties config;
    public TokenService(DevProofProperties config) { this.config = config; }

    public String hashPassword(String password) {
        byte[] salt=new byte[16]; new java.security.SecureRandom().nextBytes(salt);
        PBEKeySpec key=new PBEKeySpec(password.toCharArray(),salt,310000,256);
        try {
            byte[] digest=SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(key).getEncoded();
            Base64.Encoder padded=Base64.getUrlEncoder();
            return "pbkdf2_sha256$310000$"+padded.encodeToString(salt)+"$"+padded.encodeToString(digest);
        } catch(java.security.GeneralSecurityException e) { throw new IllegalStateException(e); }
        finally { key.clearPassword(); }
    }

    public boolean verifyPassword(String password, String encoded) {
        try {
            String[] parts = encoded.split("\\$", -1);
            if (parts.length != 4 || !parts[0].equals("pbkdf2_sha256") || !parts[1].equals("310000")) return false;
            byte[] salt = Base64.getUrlDecoder().decode(parts[2]);
            PBEKeySpec key = new PBEKeySpec(password.toCharArray(), salt, 310000, 256);
            try {
                byte[] actual = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(key).getEncoded();
                return MessageDigest.isEqual(actual, Base64.getUrlDecoder().decode(parts[3]));
            } finally { key.clearPassword(); }
        } catch (java.security.GeneralSecurityException | IllegalArgumentException e) { return false; }
    }

    public String issue(UUID userId) {
        String header = encode(Json.write(Map.of("alg", "HS256", "typ", "JWT")));
        String payload = encode(Json.write(Map.of("sub", userId.toString(), "exp", Instant.now().getEpochSecond() + config.tokenTtlSeconds())));
        String data = header + "." + payload;
        return data + "." + ENCODER.encodeToString(sign(data));
    }

    public UUID decode(String token) {
        try {
            String[] parts = token.split("\\.", -1);
            if (parts.length != 3) throw new IllegalArgumentException();
            Map<String, Object> header = Json.object(decodePart(parts[0]));
            if (!"HS256".equals(header.get("alg"))) throw new IllegalArgumentException();
            if (!MessageDigest.isEqual(sign(parts[0] + "." + parts[1]), Base64.getUrlDecoder().decode(parts[2]))) throw new IllegalArgumentException();
            Map<String, Object> payload = Json.object(decodePart(parts[1]));
            if (!(payload.get("exp") instanceof Number expiry) || expiry.longValue() <= Instant.now().getEpochSecond()) throw new IllegalArgumentException();
            return UUID.fromString((String) payload.get("sub"));
        } catch (RuntimeException e) { throw new ApiProblem(401, "AUTH_INVALID", "无效或已过期的 Token"); }
    }

    private byte[] sign(String text) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(config.jwtSecret().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return mac.doFinal(text.getBytes(StandardCharsets.US_ASCII));
        } catch (java.security.GeneralSecurityException e) { throw new IllegalStateException(e); }
    }
    private static String encode(String text) { return ENCODER.encodeToString(text.getBytes(StandardCharsets.UTF_8)); }
    private static String decodePart(String text) { return new String(Base64.getUrlDecoder().decode(text), StandardCharsets.UTF_8); }
}
