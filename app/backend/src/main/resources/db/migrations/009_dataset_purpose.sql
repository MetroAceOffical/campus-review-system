ALTER TABLE ml_dataset ADD COLUMN purpose VARCHAR(16) NOT NULL DEFAULT 'UNSET',
 ADD CONSTRAINT chk_dataset_purpose CHECK (purpose IN ('UNSET','LIBRARY','TRAIN','BOTH')),
 ADD CONSTRAINT chk_dataset_kind_purpose CHECK (kind='NEWS' OR purpose IN ('UNSET','TRAIN'));
