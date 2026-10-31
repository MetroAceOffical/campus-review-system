ALTER TABLE model_release
 ADD COLUMN bundle_id CHAR(36) NULL,
 ADD COLUMN bundle_snapshot_json JSON NULL,
 ADD CONSTRAINT fk_release_bundle FOREIGN KEY(bundle_id) REFERENCES ml_pipeline(id);
