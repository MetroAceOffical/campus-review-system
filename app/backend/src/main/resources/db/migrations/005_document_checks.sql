CREATE TABLE IF NOT EXISTS document_check (
 id CHAR(36) PRIMARY KEY, manuscript_id BIGINT NOT NULL, submission_version_id BIGINT,
 kind VARCHAR(32) NOT NULL, status VARCHAR(24) NOT NULL, input_sha256 CHAR(64) NOT NULL,
 payload_json JSON NOT NULL, result_json JSON, error_message VARCHAR(1000), created_by BIGINT NOT NULL,
 created_at DATETIME(3) NOT NULL, started_at DATETIME(3), finished_at DATETIME(3), retry_after DATETIME(3),
 FOREIGN KEY(manuscript_id) REFERENCES manuscript(id), FOREIGN KEY(submission_version_id) REFERENCES submission_version(id),
 FOREIGN KEY(created_by) REFERENCES app_user(id), INDEX(status,retry_after,created_at), INDEX(manuscript_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS document_check_event (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, check_id CHAR(36) NOT NULL, payload_json JSON NOT NULL,
 created_at DATETIME(3) NOT NULL, FOREIGN KEY(check_id) REFERENCES document_check(id), INDEX(check_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
