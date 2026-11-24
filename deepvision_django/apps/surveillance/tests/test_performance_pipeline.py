"""Focused unit tests for camera performance repairs and honest model/telemetry reporting."""

import json
import os
from unittest.mock import patch

import cv2
import numpy as np
from django.apps import apps as django_apps
from django.conf import settings
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase

from apps.accounts.models import User
from apps.cameras.models import Camera
from apps.surveillance.ai.model_loader import reset_shared_yolo_model
from apps.surveillance.ai.onnx_runtime import (
    _InferenceBuffers,
    get_effective_cpu_count,
    get_model_profile_catalog,
    resolve_selected_model_name,
)
from apps.surveillance.ai.registry import InferenceRegistry
from apps.surveillance.ai.workers import InferenceWorker
from apps.surveillance.camera.workers import CameraWorker


class PerformancePipelineUnitTests(SimpleTestCase):
    def test_inference_buffers_prepare_and_lowlight_shape(self):
        bufs = _InferenceBuffers(640)
        bright = np.full((360, 640, 3), 150, dtype=np.uint8)
        blob, scale, pad_l, pad_t = bufs.prepare(bright, 640)
        self.assertEqual(blob.shape, (1, 3, 640, 640))
        self.assertEqual(blob.dtype, np.float32)
        self.assertAlmostEqual(scale, 1.0, places=4)
        self.assertEqual(pad_l, 0.0)
        self.assertGreater(pad_t, 100.0)
        self.assertLessEqual(float(blob.max()), 1.0)
        self.assertGreaterEqual(float(blob.min()), 0.0)

        dark = np.full((360, 640, 3), 25, dtype=np.uint8)
        blob_d, _, _, _ = bufs.prepare(dark, 640)
        self.assertEqual(blob_d.shape, (1, 3, 640, 640))

    def test_model_profile_catalog_and_resolution(self):
        catalog = get_model_profile_catalog()
        ids = {c["id"]: c["model_name"] for c in catalog}
        self.assertEqual(ids.get("balanced"), "yolo26s.onnx")
        self.assertEqual(ids.get("lightweight"), "yolo26n.onnx")
        self.assertEqual(resolve_selected_model_name("balanced"), "yolo26s.onnx")
        self.assertEqual(resolve_selected_model_name("lightweight"), "yolo26n.onnx")

    def test_effective_cpu_count_respects_override(self):
        with patch.dict(os.environ, {"DEEPVISION_CPU_THREADS": "2"}):
            self.assertEqual(get_effective_cpu_count(), 2)

    def test_telemetry_summary_includes_percentiles_and_profile(self):
        worker = InferenceWorker(camera_id=999, tracker=None)
        worker.latency_samples.extend([120.0, 240.0, 360.0])
        worker.latency_ms = 240.0
        worker.last_frame_age_ms = 31.5
        summary = worker.get_telemetry_summary()
        self.assertEqual(summary["p50_latency_ms"], 240.0)
        self.assertGreaterEqual(summary["p95_latency_ms"], 348.0)
        self.assertEqual(summary["frame_age_ms"], 31.5)
        self.assertIn(summary["ai_profile"], ("balanced", "lightweight"))

    def test_registry_apply_runtime_settings_reloads_model_on_profile_change(self):
        with patch.dict(os.environ, {}, clear=False):
            reg = InferenceRegistry()
            with patch("apps.surveillance.ai.model_loader.reload_shared_yolo_model") as mock_reload, patch.object(
                reg, "_persist_settings", return_value=None
            ):
                reg.apply_runtime_settings(ai_profile="balanced")
                mock_reload.assert_called_with("balanced")
                self.assertEqual(reg.get_runtime_settings()["ai_profile"], "balanced")
                reg.apply_runtime_settings(ai_profile="lightweight")
                mock_reload.assert_called_with("lightweight")
                self.assertEqual(reg.get_runtime_settings()["ai_profile"], "lightweight")


class BinaryIngestAndDashboardTests(TransactionTestCase):
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
        Camera.objects.all().delete()
        User.objects.all().delete()
        self.user = User.objects.create(
            email="perf_test_op@example.com",
            full_name="Perf Operator",
            role="admin",
            is_email_verified=True,
            is_active=True,
        )
        self.user.set_password("StrongTestPass!2026")
        self.user.save()
        session = self.client.session
        session["user_id"] = self.user.id
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        self.camera = Camera.objects.create(
            user=self.user,
            name="Perf Browser Cam",
            source_type="browser",
            source="browser-0",
            location="Lobby",
            status="offline",
            is_active=True,
        )

    def tearDown(self):
        from apps.surveillance.camera.registry import get_camera_registry
        from apps.surveillance.ai.registry import get_inference_registry
        try:
            get_inference_registry().remove_worker(self.camera.id)
            get_camera_registry().remove_camera(self.camera.id)
        except Exception:
            pass
        try:
            Camera.objects.all().delete()
            User.objects.all().delete()
        except Exception:
            pass
        reset_shared_yolo_model()

    def test_binary_jpeg_ingest_with_seq_and_honest_dashboard_fps(self):
        img = np.full((240, 320, 3), 128, dtype=np.uint8)
        ok, enc = cv2.imencode(".jpg", img)
        self.assertTrue(ok)
        raw_jpeg = enc.tobytes()

        with patch("apps.surveillance.ai.workers.InferenceWorker.start", lambda self, cw: None):
            resp = self.client.post(
                f"/api/cameras/{self.camera.id}/ingest-frame/?seq=7",
                data=raw_jpeg,
                content_type="image/jpeg",
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["seq"], 7)
            self.assertIn("p50_latency_ms", data)
            self.assertIn("p95_latency_ms", data)

        dash_resp = self.client.get("/api/dashboard/stats/")
        self.assertEqual(dash_resp.status_code, 200)
        dash_data = dash_resp.json()
        # Honest FPS: 0.0 when only 1 frame pushed, never hardcoded 28
        self.assertNotEqual(dash_data["system_health"]["fps"], 28)

    def test_detection_settings_returns_ai_profile_and_catalog(self):
        resp = self.client.get("/api/settings/detection/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("ai_profile", data)
        self.assertIn("model_catalog", data)
        self.assertIn("effective_cpus", data)

        with patch("apps.surveillance.ai.model_loader.reload_shared_yolo_model") as mock_reload, patch(
            "apps.surveillance.ai.registry.InferenceRegistry._persist_settings", return_value=None
        ), patch.dict(os.environ, {}, clear=False):
            bal_resp = self.client.post(
                "/api/settings/detection/",
                data=json.dumps({"ai_profile": "balanced", "confidence_threshold": 0.35}),
                content_type="application/json",
            )
            self.assertEqual(bal_resp.status_code, 200)
            self.assertEqual(bal_resp.json()["ai_profile"], "balanced")
            mock_reload.assert_called_with("balanced")

            post_resp = self.client.post(
                "/api/settings/detection/",
                data=json.dumps({"ai_profile": "lightweight", "confidence_threshold": 0.4}),
                content_type="application/json",
            )
            self.assertEqual(post_resp.status_code, 200)
            post_data = post_resp.json()
            self.assertEqual(post_data["ai_profile"], "lightweight")
            mock_reload.assert_called_with("lightweight")

