from unittest.mock import patch

from django.test import SimpleTestCase

from apps.surveillance.ai.reid import GlobalIdentityRegistry


class GlobalIdentityRegistryTests(SimpleTestCase):
    def test_new_local_track_is_not_reported_as_confirmed_identity(self):
        registry = GlobalIdentityRegistry()

        global_id, status, certainty = registry.resolve_person(4, 12, timestamp=100.0)
        same_id, same_status, same_certainty = registry.resolve_person(4, 12, timestamp=101.0)

        self.assertEqual(global_id, same_id)
        self.assertEqual((status, certainty), ("UNCERTAIN", "LOW"))
        self.assertEqual((same_status, same_certainty), ("UNCERTAIN", "LOW"))
        self.assertEqual(registry.global_persons[global_id]["reid_confidence"], 0.0)

    def test_person_ids_do_not_collide_between_registry_runs(self):
        first_id, _, _ = GlobalIdentityRegistry().resolve_person(4, 12, timestamp=100.0)
        second_id, _, _ = GlobalIdentityRegistry().resolve_person(4, 12, timestamp=100.0)

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(first_id.split("-")[1], second_id.split("-")[1])

    def test_expired_camera_track_enters_reidentification_buffer(self):
        registry = GlobalIdentityRegistry()
        seen = {}
        global_id, _, _ = registry.resolve_person(4, 12, timestamp=100.0)
        registry.reconcile_camera_tracks(4, {12}, seen, timestamp=100.0)
        registry.reconcile_camera_tracks(4, set(), seen, timestamp=101.9)
        self.assertNotIn(12, registry.local_to_global)
        self.assertFalse(registry.lost_persons)

        registry.reconcile_camera_tracks(4, set(), seen, timestamp=102.1)
        self.assertNotIn(12, seen)
        self.assertEqual(registry.lost_persons[0]["global_id"], global_id)

    def test_histogram_match_is_reported_as_probable_not_confirmed(self):
        registry = GlobalIdentityRegistry()
        global_id, _, _ = registry.resolve_person(4, 12, timestamp=100.0)
        registry.handle_lost_track(4, 12, timestamp=101.0)

        with patch.object(registry, "calculate_hsv_histogram", return_value=object()), patch.object(
            registry, "compare_histograms", return_value=0.9
        ):
            matched_id, status, certainty = registry.resolve_person(5, 24, crop=object(), timestamp=102.0)

        self.assertEqual(matched_id, global_id)
        self.assertEqual((status, certainty), ("PROBABLE", "MEDIUM"))
