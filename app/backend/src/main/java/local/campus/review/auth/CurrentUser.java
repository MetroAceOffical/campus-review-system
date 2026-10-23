package local.campus.review.auth;

import java.util.*;

public record CurrentUser(String userId,String displayName,Role role,Set<String> organizationIds,List<Organization> organizations) {
    public enum Role { MEMBER, REVIEWER, ADMIN }
    public record Organization(String organizationId,String name) {}
}
