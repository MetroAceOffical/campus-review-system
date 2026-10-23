package local.campus.review.auth;

import local.campus.review.common.Api;
import local.campus.review.common.ApiException;
import org.springframework.context.annotation.*;
import org.springframework.security.authentication.*;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.*;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.*;
import org.springframework.security.web.csrf.*;
import org.springframework.security.web.authentication.session.*;
import java.util.List;

@Configuration
public class SecurityConfig {
    @Bean PasswordEncoder passwords() { return PasswordEncoderFactories.createDelegatingPasswordEncoder(); }
    @Bean UserDetailsService userDetails(UserMapper users) {
        return username -> {
            var row=users.find(username);
            if(row==null) throw new UsernameNotFoundException("Unknown account");
            return User.withUsername(row.username()).password(row.passwordHash()).roles(row.role()).disabled(!row.enabled()).build();
        };
    }
    @Bean AuthenticationManager authenticationManager(UserDetailsService users,PasswordEncoder passwords) {
        var provider=new DaoAuthenticationProvider(users); provider.setPasswordEncoder(passwords);
        return new ProviderManager(provider);
    }
    @Bean SecurityContextRepository contexts() { return new HttpSessionSecurityContextRepository(); }
    @Bean CsrfTokenRepository csrfTokens() { return new HttpSessionCsrfTokenRepository(); }
    @Bean SessionAuthenticationStrategy sessionStrategy(CsrfTokenRepository csrfTokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(new ChangeSessionIdAuthenticationStrategy(),new CsrfAuthenticationStrategy(csrfTokens)));
    }
    @Bean SecurityFilterChain security(HttpSecurity http,CurrentUserService current,SecurityContextRepository contexts,CsrfTokenRepository csrfTokens) throws Exception {
        http.csrf(csrf -> csrf.csrfTokenRepository(csrfTokens))
            .securityContext(context -> context.securityContextRepository(contexts))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/auth/csrf","/api/auth/login").permitAll()
                .requestMatchers("/api/experiments/**","/api/references/**").access((authentication,context) -> {
                    try { return new AuthorizationDecision(current.require(authentication.get()).role()==CurrentUser.Role.ADMIN); }
                    catch(ApiException e) { return new AuthorizationDecision(false); }
                })
                .requestMatchers("/api/**").authenticated().anyRequest().permitAll())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request,response,e) -> Api.writeError(response,401,"LOGIN_REQUIRED","请先登录"))
                .accessDeniedHandler((request,response,e) -> Api.writeError(response,403,e instanceof CsrfException ? "CSRF_INVALID" : "ACCESS_DENIED",e instanceof CsrfException ? "登录校验已失效，请重试" : "无权访问此内容")))
            .logout(logout -> logout.logoutUrl("/api/auth/logout").invalidateHttpSession(true).deleteCookies("JSESSIONID")
                .logoutSuccessHandler((request,response,authentication) -> {
                    response.setContentType("application/json;charset=UTF-8");
                    new com.fasterxml.jackson.databind.ObjectMapper().writeValue(response.getOutputStream(),Api.ok(java.util.Map.of("loggedOut",true)));
                }));
        return http.build();
    }
}
