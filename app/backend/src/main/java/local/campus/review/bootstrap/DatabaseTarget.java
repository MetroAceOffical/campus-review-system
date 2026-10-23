package local.campus.review.bootstrap;

import java.net.URI;

public final class DatabaseTarget {
    private DatabaseTarget() {}
    public static void requireTest(String jdbcUrl) {
        if (jdbcUrl == null || !jdbcUrl.startsWith("jdbc:mysql://")) throw new IllegalArgumentException("Missing MySQL test URL");
        var uri = URI.create(jdbcUrl.substring(5));
        if (!"127.0.0.1".equals(uri.getHost()) || uri.getPort() != 3308
                || !"/campus_review_midterm_test".equals(uri.getPath())) {
            throw new IllegalArgumentException("Tests require isolated 127.0.0.1:3308/campus_review_midterm_test");
        }
    }
}
