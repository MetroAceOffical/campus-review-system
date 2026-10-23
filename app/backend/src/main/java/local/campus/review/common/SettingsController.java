package local.campus.review.common;
import local.campus.review.auth.CurrentUserService;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
public class SettingsController {
    private final RuntimeSettings settings;
    private final CurrentUserService users;
    public SettingsController(RuntimeSettings settings,CurrentUserService users){this.settings=settings;this.users=users;}
    @GetMapping("/api/settings/limits") Api limits(Authentication authentication){users.require(authentication);return Api.ok(settings.limits());}
}
