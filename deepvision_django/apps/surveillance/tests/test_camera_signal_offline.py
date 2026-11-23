"""Regression tests for Camera SIGNAL OFFLINE vs ONLINE truthfulness, stream timeouts, recovery, and RBAC."""

import time
from unittest.mock import patch

import numpy as np
from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.core.models import AuditLog
from apps.surveillance.ai.registry import get_inference_registry
from apps.surveillance.camera.registry import get_camera_registry
from apps.surveillance.camera.workers import CameraWorker
from apps.surveillance.health.health_service import (
    get_live_camera_status,
    update_camera_health,
)
from apps.surveillance.streaming.stream_service import (
    generate_raw_stream,
    generate_tracking_stream,
)


class CameraSignalOfflineRegressionTests(TransactionTestCase):
    _created_unmanaged_models = []

    @classmethod
    def setUpClass(cls):
        existing = set(connection.introspection.table_names())
        unmanaged = [m for m in django_apps.get_models() if not m._meta.managed]
        cls._created_unmanaged_models = []
        with connection.constraint_checks_disabled():
            with connection.schema_editor() as editor:
                for model in unmanaged:
                    if model._meta.db_table not in existing:
                        editor.create_model(model)
                        existing.add(model._meta.db_table)
                        cls._created_unmanaged_models.append(model)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if cls._created_unmanaged_models:
            with connection.constraint_checks_disabled():
                with connection.schema_editor() as editor:
                    for model in reversed(cls._created_unmanaged_models):
                        try:
                            editor.delete_model(model)
                        except Exception:
                            pass

    def setUp(self):
        AuditLog.objects.all().delete()
        Camera.objects.all().delete()
        User.objects.all().delete()
        self.owner = User.objects.create(
            email="signal_owner@example.com",
            full_name="Signal Owner",
            role="operator",
            is_email_verified=True,
            is_active=True,
        )
        self.owner.set_password("StrongPass!2026")
        self.owner.save()

        self.other_user = User.objects.create(
            email="other_user@example.com",
            full_name="Other User",
            role="user",
            is_email_verified=True,
            is_active=True,
        )
        self.other_user.set_password("StrongPass!2026")
        self.other_user.save()

        self.cam = Camera.objects.create(
            user=self.owner,
            name="d",
            source_type="webcam",
            source="0",
            location="Gate-1",
            status="online",  # Stale DB flag that previously fooled UI/APIs
            is_active=True,
        )
        self.cam_browser_2 = Camera.objects.create(
            user=self.owner,
            name="Browser 2",
            source_type="browser",
            source="0",
            location="Gate-2",
            status="offline",
            is_active=True,
        )
        self._login(self.owner)

    def tearDown(self):
        cam_reg = get_camera_registry()
        inf_reg = get_inference_registry()
        for cid in (self.cam.id, self.cam_browser_2.id, 991, 992):
            try:
                inf_reg.remove_worker(cid)
            except Exception:
                pass
            try:
                cam_reg.remove_camera(cid)
            except Exception:
                pass
        try:
            AuditLog.objects.all().delete()
            Camera.objects.all().delete()
            User.objects.all().delete()
        except Exception:
            pass

    def _login(self, user):
        session = self.client.session
        session["user_id"] = user.id
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def test_online_db_camera_with_dead_worker_reports_offline_across_apis(self):
        # Database says status="online", but no live CameraWorker is running.
        list_resp = self.client.get("/api/cameras/")
        self.assertEqual(list_resp.status_code, 200)
        cams = list_resp.json()["cameras"]
        cam_row = next(c for c in cams if c["id"] == self.cam.id)
        self.assertEqual(cam_row["status"], "offline")
        self.assertFalse(cam_row["live"])

        detail_resp = self.client.get(f"/api/cameras/{self.cam.id}/")
        self.assertEqual(detail_resp.status_code, 200)
        self.assertEqual(detail_resp.json()["camera"]["status"], "offline")

        stats_resp = self.client.get(f"/api/cameras/{self.cam.id}/stats/")
        self.assertEqual(stats_resp.status_code, 200)
        stats_data = stats_resp.json()
        self.assertEqual(stats_data["status"], "offline")
        self.assertFalse(stats_data["live"])
        self.assertEqual(stats_data["fps"], 0.0)

        dash_resp = self.client.get("/api/dashboard/stats/")
        self.assertEqual(dash_resp.status_code, 200)
        self.assertEqual(dash_resp.json()["online_cameras"], 0)

    def test_worker_without_fresh_frames_transitions_connecting_stale_offline(self):
        cw = CameraWorker(camera_id=991, cap_source="browser:991", source_type="browser", user_id=self.owner.id)
        cw.start_browser_mode()
        self.assertEqual(cw.get_operational_status(), "CONNECTING")
        self.assertEqual(get_live_camera_status(991, worker=cw)["status"], "connecting")

        # Simulate stale frame > 8s ago and > 16s ago
        cw.last_valid_frame_time = time.time() - 8.5
        self.assertEqual(cw.get_operational_status(), "STALE")
        self.assertEqual(get_live_camera_status(991, worker=cw)["status"], "stale")

        cw.last_valid_frame_time = time.time() - 16.5
        self.assertEqual(cw.get_operational_status(), "OFFLINE")
        self.assertEqual(get_live_camera_status(991, worker=cw)["status"], "offline")

        # Fresh frame restores ONLINE immediately
        frame = np.full((240, 320, 3), 120, dtype=np.uint8)
        cw.ingest_external_frame(frame)
        self.assertEqual(cw.get_operational_status(), "ONLINE")
        self.assertTrue(get_live_camera_status(991, worker=cw)["live"])
        cw.stop()

    def test_offline_snapshot_returns_503_and_recovers_to_200_with_live_frame(self):
        # Even though DB says online, dead capture on /snapshot/ must return 503 + X-DeepVision-Signal: offline
        with patch("apps.ai.engine.warm_camera_capture_only", return_value=False), patch(
            "apps.ai.engine.get_camera_snapshot", return_value=None
        ):
            snap_off = self.client.get(f"/api/cameras/{self.cam.id}/snapshot/?mode=tracking")
            self.assertEqual(snap_off.status_code, 503)
            self.assertEqual(snap_off["X-DeepVision-Signal"], "offline")

        # Now feed a genuine live frame into browser worker and verify recovery -> 200 live + stats ONLINE
        cam_reg = get_camera_registry()
        cw = cam_reg.get_or_create_browser_worker(self.cam_browser_2.id, self.owner.id)
        frame = np.full((240, 320, 3), 140, dtype=np.uint8)
        cw.ingest_external_frame(frame)

        snap_live = self.client.get(f"/api/cameras/{self.cam_browser_2.id}/snapshot/?mode=raw")
        self.assertEqual(snap_live.status_code, 200)
        self.assertEqual(snap_live["X-DeepVision-Signal"], "live")
        self.assertGreater(len(snap_live.content), 512)

        stats_live = self.client.get(f"/api/cameras/{self.cam_browser_2.id}/stats/")
        self.assertEqual(stats_live.status_code, 200)
        self.assertEqual(stats_live.json()["status"], "online")
        self.assertTrue(stats_live.json()["live"])

    def test_valid_raw_and_tracking_mjpeg_streams_and_disconnect_cleanup(self):
        cam_reg = get_camera_registry()
        cw = cam_reg.get_or_create_browser_worker(self.cam_browser_2.id, self.owner.id)
        frame = np.full((240, 320, 3), 130, dtype=np.uint8)
        cw.ingest_external_frame(frame)

        # Raw stream yields valid multipart JPEG chunk and cleans up on close
        raw_gen = generate_raw_stream(self.cam_browser_2.id, self.owner.id)
        raw_chunk = next(raw_gen)
        self.assertIn(b"--frame\r\nContent-Type: image/jpeg", raw_chunk)
        raw_gen.close()

        # Tracking stream yields valid annotated chunk and degrades safely if annotation raises once
        with patch("apps.surveillance.ai.workers.InferenceWorker.start", lambda self, w: None):
            cw.ingest_external_frame(frame)
            trk_gen = generate_tracking_stream(self.cam_browser_2.id, self.owner.id)
            trk_chunk = next(trk_gen)
            self.assertIn(b"--frame\r\nContent-Type: image/jpeg", trk_chunk)
            with patch(
                "apps.surveillance.streaming.stream_service.render_annotated_frame",
                side_effect=RuntimeError("transient overlay fault"),
            ):
                cw.ingest_external_frame(frame)
                fallback_chunk = next(trk_gen)
                self.assertIn(b"--frame\r\nContent-Type: image/jpeg", fallback_chunk)
            trk_gen.close()

    def test_stream_generator_exits_cleanly_when_frames_freeze(self):
        cw = CameraWorker(camera_id=992, cap_source="browser:992", source_type="browser", user_id=self.owner.id)
        cw.start_browser_mode()
        frame = np.full((240, 320, 3), 100, dtype=np.uint8)
        cw.ingest_external_frame(frame)

        class _SingleCamReg:
            def get_worker(self, cid, uid):
                return cw

            def get_active_worker(self, cid):
                return cw

            def release_worker(self, cid):
                pass

        # Advance monotonic clock cleanly past stale timeout on 2nd iteration so generator must break rather than hang
        t_seq = [100.0, 100.1, 100.2, 115.0, 115.1, 115.2]

        def _fake_mono():
            return t_seq.pop(0) if t_seq else 120.0

        with patch("apps.surveillance.streaming.stream_service.get_camera_registry", return_value=_SingleCamReg()), patch(
            "apps.surveillance.streaming.stream_service.time.monotonic", side_effect=_fake_mono
        ):
            gen = generate_raw_stream(992, self.owner.id)
            chunks = list(gen)
            self.assertEqual(len(chunks), 1)
        cw.stop()

    def test_browser_cameras_do_not_cross_bind_workers(self):
        other_browser = Camera.objects.create(
            user=self.owner,
            name="Browser 3",
            source_type="browser",
            source="0",
            location="Gate-3",
            status="offline",
            is_active=True,
        )
        cam_reg = get_camera_registry()
        w1 = cam_reg.get_or_create_browser_worker(self.cam_browser_2.id, self.owner.id)
        self.assertIs(cam_reg.get_active_worker(self.cam_browser_2.id), w1)
        self.assertIsNone(cam_reg.get_active_worker(other_browser.id))

    def test_authenticated_and_unauthorized_stream_access(self):
        # Owner gets valid StreamingHttpResponse headers (multipart/x-mixed-replace)
        with patch("apps.cameras.views.stream_camera_frames", return_value=iter([b"--frame\r\n\r\n"])):
            ok_resp = self.client.get(f"/api/cameras/{self.cam.id}/stream/?mode=tracking")
            self.assertEqual(ok_resp.status_code, 200)
            self.assertIn("multipart/x-mixed-replace", ok_resp["Content-Type"])
            self.assertEqual(ok_resp["X-Accel-Buffering"], "no")

        # Another standard user must not access operator/private camera stream or stats
        other_cam = Camera.objects.create(
            user=self.other_user,
            name="Private Cam",
            source_type="browser",
            source="0",
            location="Office",
            status="offline",
            is_active=True,
        )
        self.other_user_2 = User.objects.create(
            email="third@example.com",
            full_name="Third User",
            role="user",
            is_email_verified=True,
            is_active=True,
        )
        self._login(self.other_user_2)
        forb_stream = self.client.get(f"/api/cameras/{other_cam.id}/stream/?mode=raw")
        self.assertEqual(forb_stream.status_code, 404)

        # Unauthenticated request must return 401
        self.client.cookies.clear()
        unauth_stream = self.client.get(f"/api/cameras/{self.cam.id}/stream/?mode=tracking")
        self.assertEqual(unauth_stream.status_code, 401)

    def test_disconnect_stops_shared_physical_worker_when_idle_siblings_not_streaming(self):
        # Two webcam cameras share source '0'; listing cameras must NOT pin sibling into _workers
        sibling = Camera.objects.create(
            user=self.owner,
            name="Sibling Webcam",
            source_type="webcam",
            source="0",
            location="Gate-4",
            status="online",
            is_active=True,
        )
        cam_reg = get_camera_registry()
        cw = CameraWorker(
            camera_id=self.cam.id,
            cap_source=0,
            source_type="webcam",
            user_id=self.owner.id,
            physical_source_id="dshow://0",
        )
        cw.running = True
        cw.last_valid_frame_time = time.time()
        cam_reg._workers[self.cam.id] = cw
        cam_reg._physical_map["dshow://0"] = cw

        # Listing cameras calls get_active_worker(sibling.id), must NOT mutate _workers[sibling.id]
        list_resp = self.client.get("/api/cameras/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertNotIn(sibling.id, cam_reg.workers)

        # Disconnecting self.cam stops the worker cleanly
        with patch.object(cw, "stop") as mock_stop:
            disc_resp = self.client.post(f"/api/cameras/{self.cam.id}/disconnect/")
            self.assertEqual(disc_resp.status_code, 200)
            mock_stop.assert_called_once()
        cw.running = False
        cam_reg._physical_map.pop("dshow://0", None)

    def test_cloud_environment_blocks_local_webcam_capture_without_device(self):
        cam_reg = get_camera_registry()
        with patch("apps.surveillance.camera.registry._has_local_capture_hardware", return_value=False), patch(
            "apps.surveillance.camera.workers.safe_open_video_capture"
        ) as mock_open:
            with self.assertRaises(RuntimeError):
                cam_reg.get_worker(self.cam.id, self.owner.id)
            mock_open.assert_not_called()
        self.cam.refresh_from_db()
        self.assertEqual(self.cam.status, "offline")

    def test_browser_ingest_monotonic_seq_webp_and_clean_disconnect_restart(self):
        import cv2
        rng = np.random.default_rng(42)
        frame = rng.integers(20, 230, size=(240, 320, 3), dtype=np.uint8)
        ok_webp, enc_webp = cv2.imencode(".webp", frame)
        self.assertTrue(ok_webp)
        webp_bytes = enc_webp.tobytes()
        self.assertGreaterEqual(len(webp_bytes), 64)

        with patch("apps.surveillance.ai.workers.InferenceWorker.start", lambda self, w: setattr(self, "running", True)):
            resp_accept = self.client.post(
                f"/api/cameras/{self.cam_browser_2.id}/ingest-frame/?seq=5",
                data=webp_bytes,
                content_type="image/webp",
            )
            self.assertEqual(resp_accept.status_code, 200)
            d1 = resp_accept.json()
            self.assertTrue(d1["success"])
            self.assertTrue(d1["accepted"])
            self.assertEqual(d1["seq"], 5)
            self.assertTrue(bool(d1.get("received_at")))

            # Out-of-order stale frame seq=3 must be ignored without overwriting latest_seq=5
            resp_stale = self.client.post(
                f"/api/cameras/{self.cam_browser_2.id}/ingest-frame/?seq=3",
                data=webp_bytes,
                content_type="image/webp",
            )
            self.assertEqual(resp_stale.status_code, 200)
            d_stale = resp_stale.json()
            self.assertFalse(d_stale["accepted"])
            self.assertTrue(d_stale["stale_sequence"])
            self.assertEqual(d_stale["latest_seq"], 5)

        inf_reg = get_inference_registry()
        iw = inf_reg.get_active_worker(self.cam_browser_2.id)
        self.assertIsNotNone(iw)
        # Simulate extra stream ref_count before disconnect
        iw.ref_count = 2

        disc_resp = self.client.post(f"/api/cameras/{self.cam_browser_2.id}/disconnect/")
        self.assertEqual(disc_resp.status_code, 200)
        self.assertIsNone(get_camera_registry().get_active_worker(self.cam_browser_2.id))
        self.assertIsNone(inf_reg.get_active_worker(self.cam_browser_2.id))
        self.assertFalse(iw.running)

        # Reconnect with fresh sequence starting at 1 must succeed
        with patch("apps.surveillance.ai.workers.InferenceWorker.start", lambda self, w: setattr(self, "running", True)):
            resp_reconn = self.client.post(
                f"/api/cameras/{self.cam_browser_2.id}/ingest-frame/?seq=1",
                data=webp_bytes,
                content_type="image/webp",
            )
            self.assertEqual(resp_reconn.status_code, 200)
            self.assertTrue(resp_reconn.json()["accepted"])
            self.assertEqual(resp_reconn.json()["seq"], 1)

    def test_shared_physical_recording_and_partial_disconnect_preserves_sibling(self):
        from apps.ai.engine import start_camera_recording
        from apps.surveillance.recording import recording_service

        sibling = Camera.objects.create(
            user=self.owner,
            name="Sibling Shared Cam",
            source_type="webcam",
            source="0",
            location="Gate-5",
            status="online",
            is_active=True,
        )
        cam_reg = get_camera_registry()
        cw = CameraWorker(
            camera_id=self.cam.id,
            cap_source=0,
            source_type="webcam",
            user_id=self.owner.id,
            physical_source_id="dshow://0",
        )
        cw.running = True
        cw.latest_frame = np.full((240, 320, 3), 110, dtype=np.uint8)
        cw.last_valid_frame_time = time.time()
        cam_reg._workers[self.cam.id] = cw
        cam_reg._physical_map["dshow://0"] = cw

        with patch("apps.surveillance.recording.recording_service.start_recording") as mock_start_rec, patch(
            "apps.surveillance.recording.recording_service.write_frame"
        ):
            mock_start_rec.return_value = type("RecObj", (), {"id": 777})()
            rec_res = start_camera_recording(sibling.id, self.owner.id)
            self.assertEqual(rec_res["status"], "ok")

        # Sibling must now be explicitly bound in _workers so frames write to sibling recording
        self.assertIn(sibling.id, cam_reg.workers)

        # Removing primary cam keeps shared worker alive and reassigns worker.camera_id to sibling
        with patch.object(cw, "stop") as mock_stop:
            cam_reg.remove_camera(self.cam.id)
            mock_stop.assert_not_called()
            self.assertEqual(cw.camera_id, sibling.id)

            # Removing last sibling stops physical worker cleanly
            cam_reg.remove_camera(sibling.id)
            mock_stop.assert_called_once()
        cw.running = False
        cam_reg._physical_map.pop("dshow://0", None)

    def test_recording_and_http_206_playback_lifecycle(self):
        import os
        import tempfile
        from apps.ai.engine import start_camera_recording, stop_camera_recording
        from apps.recordings.models import Recording

        Recording.objects.all().delete()
        try:
            cam_reg = get_camera_registry()
            cw = cam_reg.get_or_create_browser_worker(self.cam_browser_2.id, self.owner.id)
            rng = np.random.default_rng(7)
            frame = rng.integers(10, 240, size=(240, 320, 3), dtype=np.uint8)
            cw.ingest_external_frame(frame)

            with tempfile.TemporaryDirectory() as tmpdir:
                rec_dir = os.path.join(tmpdir, "recordings")
                os.makedirs(rec_dir, exist_ok=True)
                with patch("apps.surveillance.recording.recording_service._get_recordings_dir", return_value=rec_dir), patch(
                    "apps.core.media_service.RECORDINGS_DIR", rec_dir
                ):
                    start_res = start_camera_recording(self.cam_browser_2.id, self.owner.id)
                    self.assertEqual(start_res["status"], "ok")
                    rec_id = start_res["recording_id"]

                    for _ in range(15):
                        cw.ingest_external_frame(frame)
                        time.sleep(0.05)

                    stop_res = stop_camera_recording(self.cam_browser_2.id, self.owner.id)
                    self.assertEqual(stop_res["status"], "ok")

                    rec_obj = Recording.objects.get(id=rec_id)
                    self.assertEqual(rec_obj.status, "completed")
                    self.assertGreater(rec_obj.file_size, 0)

                    view_resp = self.client.get(
                        f"/recordings/{rec_id}/view/",
                        HTTP_RANGE="bytes=0-255",
                    )
                    self.assertIn(view_resp.status_code, (200, 206))
        finally:
            Recording.objects.all().delete()

