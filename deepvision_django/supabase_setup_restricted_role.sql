-- ==============================================================================
-- DeepVision Supabase Hardening & Restricted Runtime Role Setup
-- Target: Supabase PostgreSQL (Project ref: aqmngllkiepacjrasraf)
-- Host: aws-0-ap-south-1.pooler.supabase.com (Port 5432 - Session Mode)
-- ==============================================================================

BEGIN;

-- 1. Create the dedicated restricted application role if it does not exist
-- NOTE: Replace '[YOUR_SECURE_PASSWORD]' with a strong random secret before running.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'deepvision_runtime') THEN
        CREATE ROLE deepvision_runtime WITH LOGIN PASSWORD '[YOUR_SECURE_PASSWORD]' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    ELSE
        ALTER ROLE deepvision_runtime WITH LOGIN PASSWORD '[YOUR_SECURE_PASSWORD]' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
    END IF;
END
$$;

-- 2. Grant schema usage and privileges to deepvision_runtime
GRANT USAGE ON SCHEMA public TO deepvision_runtime;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO deepvision_runtime;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO deepvision_runtime;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO deepvision_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO deepvision_runtime;

-- 3. Security Hardening: Revoke direct public API access from anon and authenticated roles
-- Because DeepVision uses Django as its trusted application tier, direct client access
-- to tables via the Supabase PostgREST Data API is revoked as defense-in-depth.
-- Guarded with role existence check so the script applies cleanly on both Supabase and vanilla PostgreSQL.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

DO $$
DECLARE
    r text;
    api_roles text[] := ARRAY['anon', 'authenticated'];
BEGIN
    FOREACH r IN ARRAY api_roles LOOP
        IF EXISTS (SELECT FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I;', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I;', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I;', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I;', r);
        END IF;
    END LOOP;
END
$$;

-- 4. Enable Row Level Security (RLS) on all 18 tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE surveillance_presets ENABLE ROW LEVEL SECURITY;
ALTER TABLE camera_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE cameras ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE detection_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_playbooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE incident_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE recordings ENABLE ROW LEVEL SECURITY;
ALTER TABLE restricted_zones ENABLE ROW LEVEL SECURITY;

-- 5. Create application service-role bypass policies for deepvision_runtime
-- This allows the Django backend to manage and query all rows securely.
DO $$
DECLARE
    tbl text;
    tables text[] := ARRAY[
        'users', 'surveillance_presets', 'camera_groups', 'cameras',
        'alerts', 'audit_logs', 'detection_profiles', 'devices',
        'evidence', 'incident_cases', 'incident_notes', 'incident_playbooks',
        'incident_policies', 'notification_preferences', 'notifications',
        'products', 'recordings', 'restricted_zones'
    ];
BEGIN
    FOREACH tbl IN ARRAY tables LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I;', 'policy_runtime_full_access', tbl);
        EXECUTE format('CREATE POLICY %I ON %I TO deepvision_runtime USING (true) WITH CHECK (true);', 'policy_runtime_full_access', tbl);
    END LOOP;
END
$$;

COMMIT;

