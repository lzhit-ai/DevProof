package ai.devproof.auth;

import ai.devproof.infrastructure.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {
    private final UserMapper users;
    private final TokenService tokens;
    private final BusinessOwnership owners;
    public RegistrationService(UserMapper users,TokenService tokens,BusinessOwnership owners) { this.users=users; this.tokens=tokens; this.owners=owners; }
    @Transactional public Map<String,Object> register(String rawName,String rawEmail,String password) {
        length(rawName,1,100); length(rawEmail,3,255); length(password,8,200);
        String name=UnicodeText.strip(rawName),email=UnicodeText.strip(rawEmail).toLowerCase(Locale.ROOT);
        if(name.isEmpty() || email.chars().filter(value->value=='@').count()!=1 || email.startsWith("@") || email.endsWith("@"))throw invalid();
        owners.requireJavaIdentity(); UUID user=UUID.randomUUID();
        if(users.register(user,email,tokens.hashPassword(password),name)!=1)throw new ApiProblem(409,"EMAIL_REGISTERED","该邮箱已注册，请直接登录");
        return Map.of("access_token",tokens.issue(user),"token_type","bearer");
    }
    private void length(String value,int min,int max) { if(value==null || value.codePointCount(0,value.length())<min || value.codePointCount(0,value.length())>max)throw invalid(); }
    private ApiProblem invalid() { return new ApiProblem(422,"INPUT_INVALID","姓名、邮箱或密码不符合注册要求"); }
}
