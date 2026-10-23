CREATE TABLE IF NOT EXISTS app_user (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, username VARCHAR(64) NOT NULL UNIQUE,
 display_name VARCHAR(64) NOT NULL, password_hash VARCHAR(255) NOT NULL,
 role VARCHAR(16) NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE,
 created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL,
 CHECK(role IN ('MEMBER','REVIEWER','ADMIN'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS organization (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(100) NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE,
 created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS organization_member (
 organization_id BIGINT NOT NULL, user_id BIGINT NOT NULL, enabled BOOLEAN NOT NULL DEFAULT TRUE,
 joined_at DATETIME(3) NOT NULL, PRIMARY KEY(organization_id,user_id),
 FOREIGN KEY(organization_id) REFERENCES organization(id), FOREIGN KEY(user_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS manuscript (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, organization_id BIGINT NOT NULL, created_by BIGINT NOT NULL,
 status VARCHAR(32) NOT NULL DEFAULT 'DRAFT', publication_state VARCHAR(32) NOT NULL DEFAULT 'NOT_PUBLISHED',
 current_submission_id BIGINT, published_version_id BIGINT, next_version_no INT NOT NULL DEFAULT 1,
 first_published_at DATETIME(3), reprint_locked_at DATETIME(3), deleted_at DATETIME(3), reprint_allowed BOOLEAN NOT NULL DEFAULT TRUE,
 created_at DATETIME(3) NOT NULL, updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(organization_id) REFERENCES organization(id), FOREIGN KEY(created_by) REFERENCES app_user(id),
 INDEX(organization_id,status,updated_at), INDEX(status,updated_at), INDEX(publication_state,updated_at),
 CHECK(next_version_no>0), CHECK(status IN ('DRAFT','PENDING','RETURNED','APPROVED','REJECTED')),
 CHECK(publication_state IN ('NOT_PUBLISHED','PUBLISHED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS manuscript_draft (
 manuscript_id BIGINT PRIMARY KEY, title VARCHAR(200) NOT NULL, schema_version VARCHAR(16) NOT NULL,
 content_json JSON NOT NULL, sources_json JSON NOT NULL, content_sha256 CHAR(64) NOT NULL,
 revision BIGINT NOT NULL DEFAULT 0, updated_by BIGINT NOT NULL, updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(manuscript_id) REFERENCES manuscript(id), FOREIGN KEY(updated_by) REFERENCES app_user(id), CHECK(revision>=0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS submission_version (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, manuscript_id BIGINT NOT NULL, version_no INT NOT NULL,
 schema_version VARCHAR(16) NOT NULL, extractor_version VARCHAR(16) NOT NULL, title VARCHAR(200) NOT NULL,
 content_json JSON NOT NULL, sources_json JSON NOT NULL, plain_text LONGTEXT NOT NULL, position_map_json JSON NOT NULL,
 content_sha256 CHAR(64) NOT NULL, lifecycle_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
 superseded_by_version_id BIGINT, withdrawn_at DATETIME(3), submitted_by BIGINT NOT NULL, submitted_at DATETIME(3) NOT NULL,
 UNIQUE(manuscript_id,version_no), UNIQUE(manuscript_id,id),
 FOREIGN KEY(manuscript_id) REFERENCES manuscript(id), FOREIGN KEY(submitted_by) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS review_decision (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, submission_version_id BIGINT NOT NULL UNIQUE, reviewer_id BIGINT NOT NULL,
 decision VARCHAR(16) NOT NULL, reason TEXT, detection_snapshot_json JSON NOT NULL, decided_at DATETIME(3) NOT NULL,
 FOREIGN KEY(submission_version_id) REFERENCES submission_version(id), FOREIGN KEY(reviewer_id) REFERENCES app_user(id),
 CHECK(decision IN ('APPROVE','RETURN','REJECT')), CHECK(decision='APPROVE' OR (reason IS NOT NULL AND CHAR_LENGTH(TRIM(reason))>0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS operation_log (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, actor_id BIGINT NOT NULL, organization_id BIGINT,
 object_type VARCHAR(32) NOT NULL, object_id BIGINT, version_id BIGINT, operation VARCHAR(48) NOT NULL,
 details_json JSON NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(actor_id) REFERENCES app_user(id), FOREIGN KEY(organization_id) REFERENCES organization(id),
 INDEX(object_type,object_id,created_at), INDEX(actor_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS stored_file (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, uploaded_by BIGINT NOT NULL, storage_key VARCHAR(255) NOT NULL UNIQUE,
 original_name VARCHAR(255) NOT NULL, sha256 CHAR(64) NOT NULL, mime_type VARCHAR(64) NOT NULL,
 size_bytes BIGINT NOT NULL, width INT NOT NULL, height INT NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(uploaded_by) REFERENCES app_user(id), INDEX(sha256), CHECK(size_bytes>0 AND width>0 AND height>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS reference_work (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, manuscript_id BIGINT UNIQUE, origin_type VARCHAR(16) NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT TRUE, created_by BIGINT NOT NULL, created_at DATETIME(3) NOT NULL,
 FOREIGN KEY(manuscript_id) REFERENCES manuscript(id), FOREIGN KEY(created_by) REFERENCES app_user(id),
 CHECK((origin_type='MANUAL' AND manuscript_id IS NULL) OR (origin_type='PUBLISHED' AND manuscript_id IS NOT NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS reference_revision (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, reference_work_id BIGINT NOT NULL, revision_no INT NOT NULL,
 submission_version_id BIGINT, title VARCHAR(200) NOT NULL, content_json JSON NOT NULL,
 source_metadata_json JSON NOT NULL, original_published_at DATETIME(3), processing_status VARCHAR(32) NOT NULL,
 artifacts_json JSON NOT NULL, created_at DATETIME(3) NOT NULL, UNIQUE(reference_work_id,revision_no),
 FOREIGN KEY(reference_work_id) REFERENCES reference_work(id), FOREIGN KEY(submission_version_id) REFERENCES submission_version(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS file_binding (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, file_id BIGINT NOT NULL, draft_manuscript_id BIGINT,
 submission_version_id BIGINT, reference_revision_id BIGINT, node_id VARCHAR(64) NOT NULL, purpose VARCHAR(32) NOT NULL,
 UNIQUE(draft_manuscript_id,node_id), UNIQUE(submission_version_id,node_id), UNIQUE(reference_revision_id,node_id),
 FOREIGN KEY(file_id) REFERENCES stored_file(id), FOREIGN KEY(draft_manuscript_id) REFERENCES manuscript_draft(manuscript_id),
 FOREIGN KEY(submission_version_id) REFERENCES submission_version(id), FOREIGN KEY(reference_revision_id) REFERENCES reference_revision(id),
 CHECK((draft_manuscript_id IS NOT NULL)+(submission_version_id IS NOT NULL)+(reference_revision_id IS NOT NULL)=1),
 CHECK(purpose IN ('BODY_IMAGE','EVIDENCE_IMAGE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS library_generation (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, status VARCHAR(32) NOT NULL, index_location VARCHAR(255) NOT NULL,
 manifest_location VARCHAR(255) NOT NULL, manifest_sha256 CHAR(64) NOT NULL,
 created_at DATETIME(3) NOT NULL, activated_at DATETIME(3), CHECK(status IN ('BUILDING','READY','ACTIVE','ARCHIVED','FAILED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS runtime_state (
 name VARCHAR(64) PRIMARY KEY, library_generation_id BIGINT, updated_at DATETIME(3) NOT NULL,
 FOREIGN KEY(library_generation_id) REFERENCES library_generation(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS detection_batch (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, submission_version_id BIGINT, scene VARCHAR(16) NOT NULL DEFAULT 'FORMAL',
 input_snapshot_key VARCHAR(100) NOT NULL, input_sha256 CHAR(64) NOT NULL, batch_no INT NOT NULL,
 library_generation_id BIGINT, pipeline_manifest_json JSON, status VARCHAR(32) NOT NULL,
 cancelled_at DATETIME(3), cancel_reason VARCHAR(32), created_at DATETIME(3) NOT NULL, started_at DATETIME(3), finished_at DATETIME(3),
 UNIQUE(submission_version_id,batch_no), FOREIGN KEY(submission_version_id) REFERENCES submission_version(id),
 FOREIGN KEY(library_generation_id) REFERENCES library_generation(id), CHECK(scene<>'FORMAL' OR submission_version_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS detection_item (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, batch_id BIGINT NOT NULL, type VARCHAR(32) NOT NULL,
 target_key VARCHAR(64) NOT NULL, image_node_id VARCHAR(64), status VARCHAR(32) NOT NULL, active_attempt_id BIGINT,
 updated_at DATETIME(3) NOT NULL, UNIQUE(batch_id,type,target_key), UNIQUE(id,active_attempt_id),
 FOREIGN KEY(batch_id) REFERENCES detection_batch(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS detection_attempt (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, item_id BIGINT NOT NULL, attempt_no INT NOT NULL, status VARCHAR(32) NOT NULL,
 model_config_json JSON NOT NULL, result_json JSON NOT NULL, started_at DATETIME(3) NOT NULL, finished_at DATETIME(3),
 error_code VARCHAR(64), error_message TEXT, UNIQUE(item_id,attempt_no), UNIQUE(item_id,id),
 FOREIGN KEY(item_id) REFERENCES detection_item(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS background_job (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, kind VARCHAR(32) NOT NULL, batch_id BIGINT, item_id BIGINT,
 reference_revision_id BIGINT, reference_work_id BIGINT, status VARCHAR(32) NOT NULL,
 owner_run_id VARCHAR(36), payload_json JSON NOT NULL, created_at DATETIME(3) NOT NULL,
 started_at DATETIME(3), finished_at DATETIME(3), error_code VARCHAR(64), error_message TEXT, INDEX(status,id),
 FOREIGN KEY(batch_id) REFERENCES detection_batch(id), FOREIGN KEY(item_id) REFERENCES detection_item(id),
 FOREIGN KEY(reference_revision_id) REFERENCES reference_revision(id), FOREIGN KEY(reference_work_id) REFERENCES reference_work(id),
 CHECK((kind='DETECT_BATCH' AND batch_id IS NOT NULL AND item_id IS NULL AND reference_revision_id IS NULL AND reference_work_id IS NULL)
 OR (kind='RETRY_ITEM' AND item_id IS NOT NULL AND batch_id IS NULL AND reference_revision_id IS NULL AND reference_work_id IS NULL)
 OR (kind='PREPARE_REFERENCE' AND reference_revision_id IS NOT NULL AND batch_id IS NULL AND item_id IS NULL AND reference_work_id IS NULL)
 OR (kind='REFRESH_LIBRARY' AND batch_id IS NULL AND item_id IS NULL AND reference_revision_id IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS idempotency_record (
 id BIGINT PRIMARY KEY AUTO_INCREMENT, actor_id BIGINT NOT NULL, operation VARCHAR(48) NOT NULL,
 request_key VARCHAR(64) NOT NULL, request_sha256 CHAR(64) NOT NULL, result_json JSON NOT NULL, created_at DATETIME(3) NOT NULL,
 UNIQUE(actor_id,operation,request_key), FOREIGN KEY(actor_id) REFERENCES app_user(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
