package local.campus.review.auth;

import local.campus.review.common.ApiException;

public final class AccessPolicy {
    private AccessPolicy() {}
    public static void requireOrganization(CurrentUser user,String organizationId) {
        if (user.role()!=CurrentUser.Role.MEMBER || !user.organizationIds().contains(organizationId)) throw new ApiException(404,"RESOURCE_NOT_FOUND","未找到可访问的稿件");
    }
    public static void requireReviewer(CurrentUser user) { requireRole(user,CurrentUser.Role.REVIEWER); }
    public static void requireAdmin(CurrentUser user) { requireRole(user,CurrentUser.Role.ADMIN); }
    private static void requireRole(CurrentUser user,CurrentUser.Role role) {
        if (user.role()!=role) throw new ApiException(403,"ACCESS_DENIED","无权执行此操作");
    }
}
