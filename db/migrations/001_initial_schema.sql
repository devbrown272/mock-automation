-- Reporting Automation — Job Tracking Schema
-- No PHI is stored here. This tracks operational metadata only.

CREATE DATABASE IF NOT EXISTS refresh_jobs
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE refresh_jobs;

CREATE TABLE IF NOT EXISTS locations (
    location_id   VARCHAR(20)  NOT NULL,
    location_name VARCHAR(100) NOT NULL,
    region        VARCHAR(50)      NULL,
    district      VARCHAR(50)      NULL,
    active        TINYINT(1)   NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (location_id),
    INDEX idx_active (active),
    INDEX idx_region (region)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS refresh_jobs (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id        VARCHAR(30)     NOT NULL,
    location_id   VARCHAR(20)     NOT NULL,
    status        ENUM('running','complete','error','timeout','skipped') NOT NULL DEFAULT 'running',
    started_at    DATETIME            NULL,
    completed_at  DATETIME            NULL,
    duration_sec  DECIMAL(8,2)        NULL
                  GENERATED ALWAYS AS (TIMESTAMPDIFF(SECOND, started_at, completed_at)) STORED,
    retry_count   TINYINT         NOT NULL DEFAULT 0,
    error_message TEXT                NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_run_location (run_id, location_id),
    INDEX idx_run_id     (run_id),
    INDEX idx_location   (location_id),
    INDEX idx_status     (status),
    INDEX idx_started_at (started_at),
    CONSTRAINT fk_rj_loc FOREIGN KEY (location_id) REFERENCES locations(location_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS run_summaries (
    run_id           VARCHAR(30)  NOT NULL,
    run_date         DATE         NOT NULL,
    total_locations  INT          NOT NULL DEFAULT 0,
    complete_count   INT          NOT NULL DEFAULT 0,
    error_count      INT          NOT NULL DEFAULT 0,
    timeout_count    INT          NOT NULL DEFAULT 0,
    success_rate     DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    avg_duration_sec DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    run_started_at   DATETIME         NULL,
    run_completed_at DATETIME         NULL,
    PRIMARY KEY (run_id),
    INDEX idx_run_date (run_date)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_log (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_time DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type VARCHAR(50)     NOT NULL,
    actor      VARCHAR(100)    NOT NULL,
    location_id VARCHAR(20)        NULL,
    run_id     VARCHAR(30)         NULL,
    detail     JSON                NULL,
    PRIMARY KEY (id),
    INDEX idx_event_time  (event_time),
    INDEX idx_event_type  (event_type),
    INDEX idx_location_id (location_id)
) ENGINE=InnoDB;

-- Seed data (20 sample locations; production pulls from HR/ERP system)
INSERT IGNORE INTO locations (location_id, location_name, region, district) VALUES
  ('1',  'Location #1001', 'Northeast', 'District A'),
  ('2',  'Location #1002', 'Northeast', 'District A'),
  ('3',  'Location #1003', 'Southeast', 'District B'),
  ('4',  'Location #1004', 'Southeast', 'District B'),
  ('5',  'Location #1005', 'Midwest',   'District C'),
  ('6',  'Location #1006', 'Midwest',   'District C'),
  ('7',  'Location #1007', 'Southwest', 'District D'),
  ('8',  'Location #1008', 'Southwest', 'District D'),
  ('9',  'Location #1009', 'West',      'District E'),
  ('10', 'Location #1010', 'West',      'District E');