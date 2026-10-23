package ai.devproof.auth;

import java.util.Map;
import java.util.UUID;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Insert;

@Mapper
public interface UserMapper {
    @Select("SELECT id,email,password_hash,display_name,status FROM users WHERE email=#{email}")
    Map<String, Object> byEmail(String email);
    @Select("SELECT id,email,display_name,status FROM users WHERE id=#{id}")
    Map<String, Object> byId(UUID id);
    @Insert("INSERT INTO users(id,email,password_hash,display_name,status) VALUES(#{id},#{email},#{password},#{name},'ACTIVE') ON CONFLICT(email) DO NOTHING")
    int register(UUID id,String email,String password,String name);
}
