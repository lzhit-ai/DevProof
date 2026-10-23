package ai.devproof;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.security.autoconfigure.UserDetailsServiceAutoConfiguration;
import ai.devproof.infrastructure.DevProofProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication(exclude = UserDetailsServiceAutoConfiguration.class)
@EnableConfigurationProperties(DevProofProperties.class)
@EnableScheduling
public class DevProofApplication {
    public static void main(String[] args) {
        if(args.length>0 && "db".equals(args[0])) { System.exit(ai.devproof.migration.SchemaMigrations.run(args));return; }
        SpringApplication.run(DevProofApplication.class, args);
    }
}
