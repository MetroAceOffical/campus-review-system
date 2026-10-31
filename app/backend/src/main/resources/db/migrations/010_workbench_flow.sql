CREATE TABLE workbench_flow (
 id CHAR(36) PRIMARY KEY,
 kind VARCHAR(16) NOT NULL,
 name VARCHAR(120) NOT NULL,
 context_json JSON NOT NULL,
 current_step VARCHAR(24) NOT NULL DEFAULT 'data',
 revision BIGINT NOT NULL DEFAULT 1,
 created_by BIGINT NOT NULL,
 created_at DATETIME(3) NOT NULL,
 updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(created_by) REFERENCES app_user(id),
 CHECK(kind IN ('UPLOAD','TRAIN','CONTINUE','LIBRARY')),
 INDEX(created_by,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
