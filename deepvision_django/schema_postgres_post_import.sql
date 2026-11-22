-- ==============================================================================
-- DeepVision Post-Import Foreign Key Constraint Attachment
-- Runs AFTER historical data import so pre-existing legacy orphan
-- notifications (IDs 3997-4011 referencing purged alerts 5007-5026) remain
-- preserved intact, while enforcing referential integrity on all future
-- notifications and cascading deletes on future alert removals.
-- ==============================================================================

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_notifications_alert') THEN
        ALTER TABLE notifications
        ADD CONSTRAINT fk_notifications_alert
        FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE NOT VALID;
    END IF;
END
$$;

COMMIT;

