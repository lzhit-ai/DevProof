package ai.devproof.modelsettings;

import ai.devproof.infrastructure.ApiProblem;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.*;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ModelKeyCipher {
    private final byte[] key;
    private final SecureRandom random=new SecureRandom();
    public ModelKeyCipher(@Value("${MODEL_CREDENTIAL_ENCRYPTION_KEY:}") String encoded) {
        if(encoded.isBlank())key=null;
        else {
            try { key=Base64.getDecoder().decode(encoded); }
            catch(IllegalArgumentException e) { throw new IllegalArgumentException("Invalid model credential encryption configuration"); }
            if(key.length!=32)throw new IllegalArgumentException("Model credential encryption requires 32 bytes");
        }
    }
    public String encrypt(UUID user,UUID credential,String secret) {
        requireKey(); byte[] iv=new byte[12]; random.nextBytes(iv);
        try {
            Cipher cipher=cipher(Cipher.ENCRYPT_MODE,user,credential,iv);
            return "v1:"+Base64.getEncoder().encodeToString(iv)+":"+Base64.getEncoder().encodeToString(cipher.doFinal(secret.getBytes(StandardCharsets.UTF_8)));
        } catch(GeneralSecurityException e) { throw unavailable(); }
    }
    public String decrypt(UUID user,UUID credential,String encrypted) {
        requireKey();
        try {
            String[] parts=encrypted.split(":",-1);
            if(parts.length!=3 || !parts[0].equals("v1"))throw new IllegalArgumentException();
            byte[] iv=Base64.getDecoder().decode(parts[1]); if(iv.length!=12)throw new IllegalArgumentException();
            return new String(cipher(Cipher.DECRYPT_MODE,user,credential,iv).doFinal(Base64.getDecoder().decode(parts[2])),StandardCharsets.UTF_8);
        } catch(GeneralSecurityException | IllegalArgumentException e) { throw unavailable(); }
    }
    private Cipher cipher(int mode,UUID user,UUID credential,byte[] iv) throws GeneralSecurityException {
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode,new SecretKeySpec(key,"AES"),new GCMParameterSpec(128,iv));
        cipher.updateAAD(("devproof:user-model:v1:"+user+":"+credential).getBytes(StandardCharsets.UTF_8));
        return cipher;
    }
    private void requireKey() { if(key==null)throw new ApiProblem(503,"MODEL_SECRET_STORAGE_NOT_CONFIGURED","服务端尚未配置个人模型凭据存储"); }
    private ApiProblem unavailable() { return new ApiProblem(503,"MODEL_SECRET_UNAVAILABLE","个人模型凭据暂时不可读取，请联系管理员检查加密配置"); }
}
