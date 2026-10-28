CREATE TABLE IF NOT EXISTS ml_model (
 id CHAR(36) PRIMARY KEY, organization_id BIGINT NOT NULL, dataset_id CHAR(36) NOT NULL,
 run_id CHAR(36) NOT NULL UNIQUE, name VARCHAR(120) NOT NULL, family VARCHAR(16) NOT NULL,
 archived BOOLEAN NOT NULL DEFAULT FALSE, manifest_json JSON NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(organization_id) REFERENCES organization(id), FOREIGN KEY(dataset_id) REFERENCES ml_dataset(id),
 FOREIGN KEY(run_id) REFERENCES ml_run(id), INDEX(organization_id,archived,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
