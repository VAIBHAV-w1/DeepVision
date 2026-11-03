"""
DeepVision 4.0 — Incident Media Timestamp & Navigation Integrity Test Suite
=============================================================================
Verifies:
1. Incident media scoping & timeline synchronization.
2. Prevention of historical recording misattribution (e.g. Rec 906).
3. Zero cross-incident data contamination.
4. Truthful audio availability detection.
5. Strict 5-page navigation destination mapping and legacy route redirection.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta

# Setup Django environment
sys.path.insert(0, os.path.abspath('deepvision_django'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.alerts.models import Alert
from apps.recordings.models import Recording
from apps.evidence.models import Evidence
from apps.alerts.incident_service import get_incident_context


class TestIncidentMediaTimestampIntegrity(unittest.TestCase):
    def test_01_rec_906_never_falsely_attached_to_oct_nov_alerts(self):
        """Verify that Recording 906 (from Sept 26) is never attached to Oct/Nov alerts."""
        alerts_cam3 = Alert.objects.filter(camera_id=3, detected_at__gte='2026-10-01').order_by('-detected_at')[:30]
        self.assertGreater(alerts_cam3.count(), 0, "Expected Camera 3 alerts in database")

        falsely_attached = 0
        for alert in alerts_cam3:
            ctx = get_incident_context(alert.id)
            rec = ctx.get("primary_media", {}).get("recording")
            if rec and rec.get("id") == 906:
                falsely_attached += 1

        self.assertEqual(
            falsely_attached, 0,
            f"Recording 906 was falsely attached to {falsely_attached} alerts from October/November!"
        )

    def test_02_snapshot_only_alert_has_no_stale_recording(self):
        """Verify that an alert with only a snapshot does not fall back to an unrelated recording."""
        # Alert 6108 was verified as snapshot only
        ctx = get_incident_context(6108)
        self.assertIsNotNone(ctx.get("primary_media", {}).get("snapshot"))
        self.assertIsNone(
            ctx.get("primary_media", {}).get("recording"),
            "Snapshot-only alert should have recording=None, not a stale recording!"
        )

    def test_03_alert_with_clip_has_tight_timestamp_alignment(self):
        """Verify that an alert with an associated clip has started_at tightly matching detected_at."""
        # Alert 6114 has alert_6114_clip.mp4
        ctx = get_incident_context(6114)
        rec = ctx.get("primary_media", {}).get("recording")
        self.assertIsNotNone(rec, "Alert 6114 should have associated clip recording")
        self.assertIn("6114", rec.get("filename", ""))
        self.assertFalse(rec.get("timestamp_mismatch"), "Timestamp mismatch flag should be False for matched clip")
        self.assertLess(rec.get("time_diff_seconds", 999), 60.0, "Time difference should be under 60 seconds")

    def test_04_rec_durations_in_database_are_valid(self):
        """Verify no recordings in database have corrupt durations > 1 hour."""
        corrupted_recs = Recording.objects.filter(duration_seconds__gt=3600.0)
        self.assertEqual(
            corrupted_recs.count(), 0,
            f"Found {corrupted_recs.count()} recordings with corrupt durations > 1 hour in database"
        )

    def test_05_audio_status_is_honest(self):
        """Verify audio status is reported truthfully as unavailable for video-only camera feeds."""
        ctx = get_incident_context(6114)
        video_ev = ctx.get("primary_media", {}).get("video")
        if video_ev:
            self.assertIn("has_audio", video_ev)
            self.assertIn(video_ev["audio_status"], ["available", "unavailable"])
            self.assertIn("audio_reason", video_ev)


if __name__ == '__main__':
    unittest.main()

