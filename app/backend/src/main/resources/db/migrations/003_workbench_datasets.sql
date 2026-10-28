CREATE TABLE IF NOT EXISTS ml_dataset (
 id CHAR(36) PRIMARY KEY, organization_id BIGINT NOT NULL, name VARCHAR(120) NOT NULL,
 kind VARCHAR(16) NOT NULL, archived BOOLEAN NOT NULL DEFAULT FALSE,
 created_by BIGINT NOT NULL, created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(organization_id) REFERENCES organization(id), FOREIGN KEY(created_by) REFERENCES app_user(id),
 CHECK(kind IN ('NEWS','PAIRS')), INDEX(organization_id,archived,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ml_dataset_version (
 id CHAR(36) PRIMARY KEY, dataset_id CHAR(36) NOT NULL, parent_version_id CHAR(36),
 stage VARCHAR(16) NOT NULL, status VARCHAR(24) NOT NULL,
 file_name VARCHAR(255) NOT NULL, sha256 CHAR(64), row_count BIGINT,
 mapping_json JSON NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(dataset_id) REFERENCES ml_dataset(id),
 FOREIGN KEY(parent_version_id) REFERENCES ml_dataset_version(id),
 CHECK(stage IN ('RAW','CLEAN')), CHECK(status IN ('READY','PROCESSING','FAILED','CANCELLED','INTERRUPTED')),
 INDEX(dataset_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ml_run (
 id CHAR(36) PRIMARY KEY, dataset_id CHAR(36) NOT NULL, input_version_id CHAR(36) NOT NULL,
 output_version_id CHAR(36), action VARCHAR(32) NOT NULL, status VARCHAR(24) NOT NULL,
 mapping_json JSON NOT NULL, options_json JSON NOT NULL, result_json JSON,
 error_message VARCHAR(1000), owner_id CHAR(36), created_by BIGINT NOT NULL,
 created_at DATETIME(3) NOT NULL, started_at DATETIME(3), finished_at DATETIME(3),
 FOREIGN KEY(dataset_id) REFERENCES ml_dataset(id), FOREIGN KEY(input_version_id) REFERENCES ml_dataset_version(id),
 FOREIGN KEY(output_version_id) REFERENCES ml_dataset_version(id), FOREIGN KEY(created_by) REFERENCES app_user(id),
 CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED','INTERRUPTED')),
 INDEX(status,created_at), INDEX(dataset_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ml_run_event (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, run_id CHAR(36) NOT NULL, payload_json JSON NOT NULL,
 created_at DATETIME(3) NOT NULL, FOREIGN KEY(run_id) REFERENCES ml_run(id), INDEX(run_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
