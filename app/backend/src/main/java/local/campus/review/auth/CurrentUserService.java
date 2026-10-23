package local.campus.review.auth;

import local.campus.review.common.ApiException;
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.stereotype.Service;
import java.util.stream.Collectors;

@Service
public class CurrentUserService {
    private final UserMapper users;
    public CurrentUserService(UserMapper users) { this.users=users; }
    public CurrentUser require(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated() || authentication instanceof AnonymousAuthenticationToken) throw new ApiException(401,"LOGIN_REQUIRED","请先登录");
        var row=users.find(authentication.getName());
        if (row==null || !row.enabled()) throw new ApiException(401,"SESSION_EXPIRED","账号不可用，请重新登录");
        var organizations=users.organizations(row.id());
        return new CurrentUser(row.id().toString(),row.displayName(),CurrentUser.Role.valueOf(row.role()),
                organizations.stream().map(CurrentUser.Organization::organizationId).collect(Collectors.toUnmodifiableSet()),organizations);
    }
}
