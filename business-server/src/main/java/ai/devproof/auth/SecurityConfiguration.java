package ai.devproof.auth;

import ai.devproof.infrastructure.DevProofProperties;
import java.util.Arrays;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfiguration {
    @Bean SecurityFilterChain security(HttpSecurity http, BearerFilter bearer) throws Exception {
        return http.csrf(csrf -> csrf.disable()).cors(cors -> {}).sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth.requestMatchers("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/health/**", "/internal/**").permitAll().anyRequest().authenticated())
                .addFilterBefore(bearer, UsernamePasswordAuthenticationFilter.class).build();
    }
    @Bean FilterRegistrationBean<BearerFilter> disableContainerRegistration(BearerFilter filter) {
        FilterRegistrationBean<BearerFilter> bean = new FilterRegistrationBean<>(filter);
        bean.setEnabled(false); return bean;
    }
    @Bean CorsConfigurationSource corsConfigurationSource(DevProofProperties properties) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(Arrays.stream(properties.corsOrigins().split(",")).map(String::trim).toList());
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type", "Idempotency-Key", "If-Match", "X-Correlation-Id"));
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource(); source.registerCorsConfiguration("/**", cors); return source;
    }
}
