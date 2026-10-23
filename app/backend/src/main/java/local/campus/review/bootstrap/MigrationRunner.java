package local.campus.review.bootstrap;

import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.sql.*;
import java.util.*;

/** Ordered immutable migrations. MySQL DDL auto-commits: failed DDL is never marked applied. */
public final class MigrationRunner {
    public record AppliedMigration(String version, String checksum) {}
    private MigrationRunner() {}

    public static List<AppliedMigration> apply(Connection db, Path directory) throws Exception {
        try (var statement = db.createStatement(); var lock = statement.executeQuery("SELECT GET_LOCK('campus_schema_migration',30)")) {
            if (!lock.next() || lock.getInt(1) != 1) throw new IllegalStateException("Migration lock unavailable");
        }
        try {
            try (var s = db.createStatement()) {
                s.execute("CREATE TABLE IF NOT EXISTS schema_migration(version VARCHAR(64) PRIMARY KEY, checksum CHAR(64) NOT NULL, applied_at DATETIME(3) NOT NULL) ENGINE=InnoDB");
            }
            var applied = new HashMap<String,String>();
            try (var s = db.createStatement(); var rows = s.executeQuery("SELECT version,checksum FROM schema_migration")) {
                while (rows.next()) applied.put(rows.getString(1),rows.getString(2));
            }
            List<Path> files;
            try (var entries = Files.list(directory)) {
                files = entries.filter(p -> p.getFileName().toString().matches("[0-9]+_[a-z0-9_]+\\.sql")).sorted().toList();
            }
            if (files.isEmpty()) throw new IllegalStateException("No migrations found");
            var checksums = new LinkedHashMap<Path,String>();
            for (var file : files) {
                String version = file.getFileName().toString();
                String checksum = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(file)));
                if (applied.containsKey(version) && !applied.get(version).equals(checksum)) {
                    throw new IllegalStateException("Applied migration checksum changed: " + version);
                }
                checksums.put(file,checksum);
            }
            var present = checksums.keySet().stream().map(p -> p.getFileName().toString()).toList();
            if (!present.containsAll(applied.keySet())) throw new IllegalStateException("Applied migration file missing");
            var result = new ArrayList<AppliedMigration>();
            for (var entry : checksums.entrySet()) {
                var version = entry.getKey().getFileName().toString();
                if (applied.containsKey(version)) continue;
                // Migration files contain simple DDL/DML, no stored routines or quoted semicolons.
                var script = Files.readString(entry.getKey(), StandardCharsets.UTF_8).replaceAll("(?m)^\\s*--.*$", "");
                for (var sql : script.split(";")) {
                    if (!sql.isBlank()) try (var s = db.createStatement()) { s.execute(sql); }
                }
                try (var s = db.prepareStatement("INSERT INTO schema_migration(version,checksum,applied_at) VALUES(?,?,UTC_TIMESTAMP(3))")) {
                    s.setString(1,version); s.setString(2,entry.getValue()); s.executeUpdate();
                }
                result.add(new AppliedMigration(version,entry.getValue()));
            }
            return List.copyOf(result);
        } finally {
            try (var s = db.createStatement()) { s.execute("SELECT RELEASE_LOCK('campus_schema_migration')"); }
        }
    }

    public static void main(String[] args) throws Exception {
        try (var db = DriverManager.getConnection(System.getenv("CAMPUS_DB_URL"), System.getenv("CAMPUS_DB_USER"), System.getenv("CAMPUS_DB_PASSWORD"))) {
            System.out.println("Applied migrations: " + apply(db,Path.of(args[0])).size());
        }
    }
}
