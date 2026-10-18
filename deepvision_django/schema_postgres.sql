-- ==============================================================================
-- DeepVision 1.1.0 PostgreSQL / Supabase Canonical Schema
-- Target: Supabase Free PostgreSQL / PostgreSQL 14+
-- Translated from canonical SQLite schema (18 tables, 11 secondary indexes)
-- ==============================================================================

BEGIN;

-- 1. Users
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL,
    is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    email_otp_hash VARCHAR(255),
    email_otp_expires_at TIMESTAMP,
    email_otp_attempts INTEGER NOT NULL DEFAULT 0,
    email_otp_sent_at TIMESTAMP,
    password_reset_otp_hash VARCHAR(255),
    password_reset_otp_expires_at TIMESTAMP,
    password_reset_otp_attempts INTEGER NOT NULL DEFAULT 0,
    password_reset_otp_sent_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

-- 2. Surveillance Presets
CREATE TABLE IF NOT EXISTS surveillance_presets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    loitering_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    restricted_entry_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    unusual_movement_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    abandoned_object_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    stationary_distance_threshold DOUBLE PRECISION,
    stationary_time_threshold DOUBLE PRECISION,
    loitering_radius DOUBLE PRECISION,
    loitering_time_threshold DOUBLE PRECISION,
    speed_fast_threshold DOUBLE PRECISION,
    speed_slow_threshold DOUBLE PRECISION,
    unusual_movement_persistence_seconds DOUBLE PRECISION,
    anomaly_event_cooldown_seconds DOUBLE PRECISION,
    anomaly_display_seconds DOUBLE PRECISION,
    abandoned_object_time_threshold DOUBLE PRECISION,
    abandoned_object_distance_threshold DOUBLE PRECISION,
    person_object_association_distance DOUBLE PRECISION,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Camera Groups
CREATE TABLE IF NOT EXISTS camera_groups (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Cameras
CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    source VARCHAR(255) NOT NULL,
    location VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'offline',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    group_id INTEGER REFERENCES camera_groups(id) ON DELETE SET NULL,
    preset_id INTEGER REFERENCES surveillance_presets(id) ON DELETE SET NULL
);

-- 5. Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    track_id INTEGER,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'new',
    confidence DOUBLE PRECISION,
    location VARCHAR(100),
    detected_at TIMESTAMP NOT NULL,
    acknowledged_at TIMESTAMP,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    response_state VARCHAR(20) DEFAULT 'NEW'
);

-- 6. Audit Logs
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(100),
    description TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id);

-- 7. Detection Profiles
CREATE TABLE IF NOT EXISTS detection_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL UNIQUE REFERENCES cameras(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    loitering_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    restricted_entry_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    unusual_movement_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    abandoned_object_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    stationary_distance_threshold DOUBLE PRECISION,
    stationary_time_threshold DOUBLE PRECISION,
    loitering_radius DOUBLE PRECISION,
    loitering_time_threshold DOUBLE PRECISION,
    speed_fast_threshold DOUBLE PRECISION,
    speed_slow_threshold DOUBLE PRECISION,
    unusual_movement_persistence_seconds DOUBLE PRECISION,
    anomaly_event_cooldown_seconds DOUBLE PRECISION,
    anomaly_display_seconds DOUBLE PRECISION,
    abandoned_object_time_threshold DOUBLE PRECISION,
    abandoned_object_distance_threshold DOUBLE PRECISION,
    person_object_association_distance DOUBLE PRECISION,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 8. Devices
CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    device_type VARCHAR(20) NOT NULL,
    identifier VARCHAR(100),
    status VARCHAR(20) NOT NULL DEFAULT 'offline',
    last_seen TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 9. Evidence
CREATE TABLE IF NOT EXISTS evidence (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    evidence_type VARCHAR(20) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    file_name VARCHAR(100) NOT NULL,
    mime_type VARCHAR(50) NOT NULL,
    file_size BIGINT NOT NULL,
    captured_at TIMESTAMP NOT NULL,
    duration_seconds DOUBLE PRECISION,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 10. Incident Cases
CREATE TABLE IF NOT EXISTS incident_cases (
    id SERIAL PRIMARY KEY,
    case_number VARCHAR(50) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    priority VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    assigned_to VARCHAR(100),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_incident_cases_case_number ON incident_cases (case_number);
CREATE INDEX IF NOT EXISTS ix_incident_cases_alert_id ON incident_cases (alert_id);
CREATE INDEX IF NOT EXISTS ix_incident_cases_user_id ON incident_cases (user_id);

-- 11. Incident Notes
CREATE TABLE IF NOT EXISTS incident_notes (
    id SERIAL PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_incident_notes_alert_id ON incident_notes (alert_id);
CREATE INDEX IF NOT EXISTS ix_incident_notes_user_id ON incident_notes (user_id);

-- 12. Incident Playbooks
CREATE TABLE IF NOT EXISTS incident_playbooks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 1,
    severity VARCHAR(20),
    event_type VARCHAR(50),
    camera_id INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    group_id INTEGER REFERENCES camera_groups(id) ON DELETE SET NULL,
    create_case BOOLEAN NOT NULL DEFAULT FALSE,
    auto_escalate BOOLEAN NOT NULL DEFAULT FALSE,
    send_notification BOOLEAN NOT NULL DEFAULT TRUE,
    notification_severity VARCHAR(20),
    apply_sla_policy BOOLEAN NOT NULL DEFAULT FALSE,
    cooldown_seconds INTEGER NOT NULL DEFAULT 300,
    last_executed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 13. Incident Policies
CREATE TABLE IF NOT EXISTS incident_policies (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    severity VARCHAR(20) NOT NULL,
    initial_response_minutes INTEGER NOT NULL,
    escalation_minutes INTEGER NOT NULL,
    resolution_minutes INTEGER NOT NULL,
    auto_escalate BOOLEAN NOT NULL DEFAULT FALSE,
    auto_create_case BOOLEAN NOT NULL DEFAULT FALSE,
    notify_on_escalation BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 14. Notification Preferences
CREATE TABLE IF NOT EXISTS notification_preferences (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    notify_critical BOOLEAN NOT NULL DEFAULT TRUE,
    notify_high BOOLEAN NOT NULL DEFAULT TRUE,
    notify_medium BOOLEAN NOT NULL DEFAULT TRUE,
    notify_low BOOLEAN NOT NULL DEFAULT FALSE,
    notify_loitering BOOLEAN NOT NULL DEFAULT TRUE,
    notify_restricted_entry BOOLEAN NOT NULL DEFAULT TRUE,
    notify_unusual_movement BOOLEAN NOT NULL DEFAULT TRUE,
    notify_abandoned_object BOOLEAN NOT NULL DEFAULT TRUE,
    notify_recording_events BOOLEAN NOT NULL DEFAULT FALSE,
    notify_system_events BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Notifications
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP
);

-- 16. Products
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    sku VARCHAR(50) NOT NULL,
    barcode VARCHAR(50),
    _reference_images TEXT NOT NULL,
    active_status BOOLEAN NOT NULL DEFAULT TRUE,
    recognition_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 17. Recordings
CREATE TABLE IF NOT EXISTS recordings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(255) NOT NULL,
    duration_seconds DOUBLE PRECISION NOT NULL,
    file_size BIGINT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_recordings_camera_id ON recordings (camera_id);
CREATE INDEX IF NOT EXISTS ix_recordings_user_id ON recordings (user_id);

-- 18. Restricted Zones
CREATE TABLE IF NOT EXISTS restricted_zones (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    x1 INTEGER NOT NULL,
    y1 INTEGER NOT NULL,
    x2 INTEGER NOT NULL,
    y2 INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
