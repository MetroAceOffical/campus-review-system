ALTER TABLE ml_model ADD COLUMN logical_model_id CHAR(36) NULL, ADD COLUMN parent_model_id CHAR(36) NULL, ADD COLUMN version_number INT NOT NULL DEFAULT 1;
UPDATE ml_model SET logical_model_id=id WHERE logical_model_id IS NULL;
ALTER TABLE ml_model MODIFY logical_model_id CHAR(36) NOT NULL, ADD UNIQUE KEY model_version(logical_model_id,version_number), ADD FOREIGN KEY(parent_model_id) REFERENCES ml_model(id);
