package local.campus.review.auth;

import jakarta.servlet.http.*;
import local.campus.review.common.*;
import org.springframework.security.authentication.*;
import org.springframework.security.core.*;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthenticationManager manager;
    private final SessionAuthenticationStrategy sessions;
    private final SecurityContextRepository contexts;
    private final CurrentUserService current;
    public AuthController(AuthenticationManager manager,SessionAuthenticationStrategy sessions,SecurityContextRepository contexts,CurrentUserService current) {
        this.manager=manager; this.sessions=sessions; this.contexts=contexts; this.current=current;
    }
    public record Credentials(String username,String password) {}
    @GetMapping("/csrf") Api csrf(CsrfToken token) { return Api.ok(Map.of("headerName",token.getHeaderName(),"token",token.getToken())); }
    @GetMapping("/me") Api me(Authentication authentication) { return Api.ok(current.require(authentication)); }
    @PostMapping("/login") Api login(@RequestBody Credentials credentials,HttpServletRequest request,HttpServletResponse response) {
        if(credentials.username()==null || credentials.password()==null || credentials.username().length()>64 || credentials.password().length()>256) throw new ApiException(400,"VALIDATION_ERROR","请填写有效的账号和密码");
        try {
            var authentication=manager.authenticate(UsernamePasswordAuthenticationToken.unauthenticated(credentials.username(),credentials.password()));
            sessions.onAuthentication(authentication,request,response);
            var context=SecurityContextHolder.createEmptyContext(); context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context); contexts.saveContext(context,request,response);
            return Api.ok(current.require(authentication));
        } catch(AuthenticationException e) { throw new ApiException(401,"BAD_CREDENTIALS","账号或密码错误"); }
    }
}
