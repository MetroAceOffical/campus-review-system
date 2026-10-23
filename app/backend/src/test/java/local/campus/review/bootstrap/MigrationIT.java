package local.campus.review.bootstrap;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.sql.*;
import static org.junit.jupiter.api.Assertions.*;

class MigrationIT {
    @TempDir Path temporary;

    @Test void reapplyPreservesExistingData() throws Exception {
        DatabaseTarget.requireTest(System.getenv("CAMPUS_TEST_DB_URL"));
        try (var db = DriverManager.getConnection(System.getenv("CAMPUS_TEST_DB_URL"),
                System.getenv("CAMPUS_TEST_DB_USER"), System.getenv("CAMPUS_TEST_DB_PASSWORD"))) {
            assertEquals("campus_review_midterm_test", db.getCatalog());
            var migrations = Path.of("src/main/resources/db/migrations");
            MigrationRunner.apply(db, migrations);
            try (var sql = db.createStatement()) {
                sql.executeUpdate("INSERT IGNORE INTO app_user(id,username,display_name,password_hash,role,enabled,created_at,updated_at) VALUES(900001,'migration_probe','迁移探针','not-a-login-hash','MEMBER',true,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))");
                sql.executeUpdate("INSERT IGNORE INTO organization(id,name,enabled,created_at,updated_at) VALUES(900001,'迁移测试组织',true,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))");
                sql.executeUpdate("INSERT IGNORE INTO manuscript(id,organization_id,created_by,status,publication_state,next_version_no,reprint_allowed,created_at,updated_at) VALUES(900001,900001,900001,'DRAFT','NOT_PUBLISHED',1,true,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))");
            }
            assertTrue(MigrationRunner.apply(db, migrations).isEmpty());
            try (var sql = db.createStatement(); var rows = sql.executeQuery("SELECT COUNT(*) FROM manuscript WHERE id=900001 AND status='DRAFT'")) {
                assertTrue(rows.next()); assertEquals(1,rows.getInt(1));
            }
            try (var sql = db.createStatement(); var rows = sql.executeQuery("SELECT COUNT(*) FROM app_user WHERE username='migration_probe'")) {
                assertTrue(rows.next()); assertEquals(1,rows.getInt(1));
            }
            try (var files = Files.list(migrations)) {
                for (var source : files.toList()) Files.copy(source, temporary.resolve(source.getFileName()));
            }
            Files.writeString(temporary.resolve("001_core.sql"), "\n-- changed checksum\n", StandardOpenOption.APPEND);
            assertThrows(IllegalStateException.class, () -> MigrationRunner.apply(db, temporary));
        }
    }

    @Test void testDatabaseGuardRejectsBusinessDatabase() {
        assertThrows(IllegalArgumentException.class, () -> DatabaseTarget.requireTest("jdbc:mysql://127.0.0.1:3308/campus_review_midterm"));
        assertThrows(IllegalArgumentException.class, () -> DatabaseTarget.requireTest("jdbc:mysql://127.0.0.1:3306/campus_review_midterm_test"));
        assertDoesNotThrow(() -> DatabaseTarget.requireTest("jdbc:mysql://127.0.0.1:3308/campus_review_midterm_test?connectionTimeZone=UTC"));
    }
}
