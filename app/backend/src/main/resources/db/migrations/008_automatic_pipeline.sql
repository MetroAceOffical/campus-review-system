CREATE TABLE ml_pipeline (
 id CHAR(36) PRIMARY KEY, dataset_id CHAR(36) NOT NULL, input_version_id CHAR(36) NOT NULL,
 name VARCHAR(120) NOT NULL, status VARCHAR(24) NOT NULL, config_json JSON NOT NULL, state_json JSON NOT NULL,
 error_message VARCHAR(1000), created_by BIGINT NOT NULL, actor_id BIGINT NOT NULL,
 created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(dataset_id) REFERENCES ml_dataset(id), FOREIGN KEY(input_version_id) REFERENCES ml_dataset_version(id),
 FOREIGN KEY(created_by) REFERENCES app_user(id), FOREIGN KEY(actor_id) REFERENCES app_user(id),
 CHECK(status IN ('QUEUED','RUNNING','COMPLETED','FAILED','BLOCKED','CANCELLED')),
 INDEX(status,created_at), INDEX(dataset_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
