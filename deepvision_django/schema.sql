CREATE TABLE alerts (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	camera_id INTEGER NOT NULL, 
	track_id INTEGER, 
	event_type VARCHAR(50) NOT NULL, 
	title VARCHAR(100) NOT NULL, 
	message TEXT NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	confidence FLOAT, 
	location VARCHAR(100), 
	detected_at DATETIME NOT NULL, 
	acknowledged_at DATETIME, 
	resolved_at DATETIME, 
	created_at DATETIME, 
	updated_at DATETIME, response_state VARCHAR(20) DEFAULT 'NEW', 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(camera_id) REFERENCES cameras (id) ON DELETE CASCADE
);

CREATE TABLE audit_logs (
	id INTEGER NOT NULL, 
	user_id INTEGER, 
	action VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(100) NOT NULL, 
	resource_id VARCHAR(100), 
	description TEXT, 
	ip_address VARCHAR(45), 
	user_agent VARCHAR(255), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE camera_groups (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description VARCHAR(255), 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE cameras (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	source_type VARCHAR(20) NOT NULL, 
	source VARCHAR(255) NOT NULL, 
	location VARCHAR(100), 
	status VARCHAR(20) NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, group_id INTEGER REFERENCES camera_groups(id) ON DELETE SET NULL, preset_id INTEGER REFERENCES surveillance_presets(id) ON DELETE SET NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE detection_profiles (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	camera_id INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	loitering_enabled BOOLEAN NOT NULL, 
	restricted_entry_enabled BOOLEAN NOT NULL, 
	unusual_movement_enabled BOOLEAN NOT NULL, 
	abandoned_object_enabled BOOLEAN NOT NULL, 
	stationary_distance_threshold FLOAT, 
	stationary_time_threshold FLOAT, 
	loitering_radius FLOAT, 
	loitering_time_threshold FLOAT, 
	speed_fast_threshold FLOAT, 
	speed_slow_threshold FLOAT, 
	unusual_movement_persistence_seconds FLOAT, 
	anomaly_event_cooldown_seconds FLOAT, 
	anomaly_display_seconds FLOAT, 
	abandoned_object_time_threshold FLOAT, 
	abandoned_object_distance_threshold FLOAT, 
	person_object_association_distance FLOAT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	UNIQUE (camera_id), 
	FOREIGN KEY(camera_id) REFERENCES cameras (id)
);

CREATE TABLE devices (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	device_type VARCHAR(20) NOT NULL, 
	identifier VARCHAR(100), 
	status VARCHAR(20) NOT NULL, 
	last_seen DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE evidence (
	id INTEGER NOT NULL, 
	alert_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	camera_id INTEGER NOT NULL, 
	evidence_type VARCHAR(20) NOT NULL, 
	file_path VARCHAR(255) NOT NULL, 
	file_name VARCHAR(100) NOT NULL, 
	mime_type VARCHAR(50) NOT NULL, 
	file_size INTEGER NOT NULL, 
	captured_at DATETIME NOT NULL, 
	duration_seconds FLOAT, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(alert_id) REFERENCES alerts (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(camera_id) REFERENCES cameras (id)
);

CREATE TABLE incident_cases (
	id INTEGER NOT NULL, 
	case_number VARCHAR(50) NOT NULL, 
	user_id INTEGER NOT NULL, 
	alert_id INTEGER, 
	title VARCHAR(200) NOT NULL, 
	description TEXT, 
	priority VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	assigned_to VARCHAR(100), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	closed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(alert_id) REFERENCES alerts (id) ON DELETE SET NULL
);

CREATE TABLE incident_notes (
	id INTEGER NOT NULL, 
	alert_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(alert_id) REFERENCES alerts (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE incident_playbooks (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	enabled BOOLEAN NOT NULL, 
	priority INTEGER NOT NULL, 
	severity VARCHAR(20), 
	event_type VARCHAR(50), 
	camera_id INTEGER, 
	group_id INTEGER, 
	create_case BOOLEAN NOT NULL, 
	auto_escalate BOOLEAN NOT NULL, 
	send_notification BOOLEAN NOT NULL, 
	notification_severity VARCHAR(20), 
	apply_sla_policy BOOLEAN NOT NULL, 
	cooldown_seconds INTEGER NOT NULL, 
	last_executed_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(camera_id) REFERENCES cameras (id) ON DELETE SET NULL, 
	FOREIGN KEY(group_id) REFERENCES camera_groups (id) ON DELETE SET NULL
);

CREATE TABLE incident_policies (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	enabled BOOLEAN NOT NULL, 
	severity VARCHAR(20) NOT NULL, 
	initial_response_minutes INTEGER NOT NULL, 
	escalation_minutes INTEGER NOT NULL, 
	resolution_minutes INTEGER NOT NULL, 
	auto_escalate BOOLEAN NOT NULL, 
	auto_create_case BOOLEAN NOT NULL, 
	notify_on_escalation BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE notification_preferences (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	notify_critical BOOLEAN NOT NULL, 
	notify_high BOOLEAN NOT NULL, 
	notify_medium BOOLEAN NOT NULL, 
	notify_low BOOLEAN NOT NULL, 
	notify_loitering BOOLEAN NOT NULL, 
	notify_restricted_entry BOOLEAN NOT NULL, 
	notify_unusual_movement BOOLEAN NOT NULL, 
	notify_abandoned_object BOOLEAN NOT NULL, 
	notify_recording_events BOOLEAN NOT NULL, 
	notify_system_events BOOLEAN NOT NULL, 
	created_at DATETIME, 
	updated_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE notifications (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	alert_id INTEGER NOT NULL, 
	is_read BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	read_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(alert_id) REFERENCES alerts (id) ON DELETE CASCADE
);

CREATE TABLE products (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	product_id VARCHAR(50) NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	category VARCHAR(50) NOT NULL, 
	sku VARCHAR(50) NOT NULL, 
	barcode VARCHAR(50), 
	_reference_images TEXT NOT NULL, 
	active_status BOOLEAN NOT NULL, 
	recognition_enabled BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE recordings (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	camera_id INTEGER NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	file_path VARCHAR(255) NOT NULL, 
	duration_seconds FLOAT NOT NULL, 
	file_size INTEGER NOT NULL, 
	started_at DATETIME NOT NULL, 
	ended_at DATETIME, 
	status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(camera_id) REFERENCES cameras (id) ON DELETE CASCADE
);

CREATE TABLE restricted_zones (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	camera_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	x1 INTEGER NOT NULL, 
	y1 INTEGER NOT NULL, 
	x2 INTEGER NOT NULL, 
	y2 INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(camera_id) REFERENCES cameras (id)
);

CREATE TABLE surveillance_presets (
	id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description VARCHAR(255), 
	enabled BOOLEAN NOT NULL, 
	loitering_enabled BOOLEAN NOT NULL, 
	restricted_entry_enabled BOOLEAN NOT NULL, 
	unusual_movement_enabled BOOLEAN NOT NULL, 
	abandoned_object_enabled BOOLEAN NOT NULL, 
	stationary_distance_threshold FLOAT, 
	stationary_time_threshold FLOAT, 
	loitering_radius FLOAT, 
	loitering_time_threshold FLOAT, 
	speed_fast_threshold FLOAT, 
	speed_slow_threshold FLOAT, 
	unusual_movement_persistence_seconds FLOAT, 
	anomaly_event_cooldown_seconds FLOAT, 
	anomaly_display_seconds FLOAT, 
	abandoned_object_time_threshold FLOAT, 
	abandoned_object_distance_threshold FLOAT, 
	person_object_association_distance FLOAT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE users (
	id INTEGER NOT NULL, 
	full_name VARCHAR(100) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	is_email_verified BOOLEAN NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, email_otp_hash VARCHAR(255), email_otp_expires_at DATETIME, email_otp_attempts INTEGER DEFAULT 0 NOT NULL, email_otp_sent_at DATETIME, password_reset_otp_hash VARCHAR(255), password_reset_otp_expires_at DATETIME, password_reset_otp_attempts INTEGER DEFAULT 0 NOT NULL, password_reset_otp_sent_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_action ON audit_logs (action);

CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at);

CREATE INDEX ix_audit_logs_user_id ON audit_logs (user_id);

CREATE INDEX ix_incident_cases_alert_id ON incident_cases (alert_id);

CREATE UNIQUE INDEX ix_incident_cases_case_number ON incident_cases (case_number);

CREATE INDEX ix_incident_cases_user_id ON incident_cases (user_id);

CREATE INDEX ix_incident_notes_alert_id ON incident_notes (alert_id);

CREATE INDEX ix_incident_notes_user_id ON incident_notes (user_id);

CREATE INDEX ix_recordings_camera_id ON recordings (camera_id);

CREATE INDEX ix_recordings_user_id ON recordings (user_id);

CREATE UNIQUE INDEX ix_users_email ON users (email);
