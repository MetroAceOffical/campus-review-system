CREATE TABLE IF NOT EXISTS model_release (
 id CHAR(36) PRIMARY KEY, organization_id BIGINT, scene VARCHAR(32) NOT NULL,
 name VARCHAR(120) NOT NULL, model_id CHAR(36), evaluation_run_id CHAR(36), preset VARCHAR(16),
 status VARCHAR(24) NOT NULL, manifest_json JSON, error_message VARCHAR(1000),
 created_by BIGINT NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(organization_id) REFERENCES organization(id), FOREIGN KEY(model_id) REFERENCES ml_model(id),
 FOREIGN KEY(created_by) REFERENCES app_user(id), INDEX(status,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS model_release_pointer (
 scope_key VARCHAR(100) PRIMARY KEY, release_id CHAR(36), updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(release_id) REFERENCES model_release(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS model_release_event (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, scope_key VARCHAR(100) NOT NULL, previous_id CHAR(36),
 release_id CHAR(36), actor_id BIGINT NOT NULL, created_at DATETIME(3) NOT NULL,
 INDEX(scope_key,id), FOREIGN KEY(actor_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS reference_import (
 id CHAR(36) PRIMARY KEY, dataset_id CHAR(36) NOT NULL, version_id CHAR(36) NOT NULL,
 created_by BIGINT NOT NULL, status VARCHAR(32) NOT NULL, processed INT NOT NULL DEFAULT 0,
 inserted INT NOT NULL DEFAULT 0, duplicates INT NOT NULL DEFAULT 0, rejected INT NOT NULL DEFAULT 0,
 generation_id BIGINT, error_message VARCHAR(1000), created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(dataset_id) REFERENCES ml_dataset(id), FOREIGN KEY(version_id) REFERENCES ml_dataset_version(id),
 FOREIGN KEY(created_by) REFERENCES app_user(id), INDEX(status,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS reference_import_row (
 batch_id CHAR(36) NOT NULL, row_no INT NOT NULL, source_id VARCHAR(255), status VARCHAR(24) NOT NULL,
 reference_work_id BIGINT, message VARCHAR(500), PRIMARY KEY(batch_id,row_no),
 FOREIGN KEY(batch_id) REFERENCES reference_import(id), FOREIGN KEY(reference_work_id) REFERENCES reference_work(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS model_release_prediction (
 id CHAR(36) PRIMARY KEY, release_id CHAR(36) NOT NULL, input_sha256 CHAR(64) NOT NULL,
 result_json JSON NOT NULL, created_by BIGINT NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(release_id) REFERENCES model_release(id), FOREIGN KEY(created_by) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
