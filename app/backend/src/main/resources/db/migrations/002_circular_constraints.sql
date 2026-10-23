ALTER TABLE manuscript ADD CONSTRAINT fk_current_submission FOREIGN KEY(id,current_submission_id) REFERENCES submission_version(manuscript_id,id);
ALTER TABLE manuscript ADD CONSTRAINT fk_published_version FOREIGN KEY(id,published_version_id) REFERENCES submission_version(manuscript_id,id);
ALTER TABLE submission_version ADD CONSTRAINT fk_superseded_version FOREIGN KEY(manuscript_id,superseded_by_version_id) REFERENCES submission_version(manuscript_id,id);
ALTER TABLE detection_item ADD CONSTRAINT fk_active_attempt FOREIGN KEY(id,active_attempt_id) REFERENCES detection_attempt(item_id,id);
