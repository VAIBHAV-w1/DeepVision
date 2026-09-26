"""
URL Configuration for DeepVision Django + React Application.
Provides:
- Production React SPA entrypoints
- Unified REST/JSON API layer for React components (/api/...)
- Protected Native Surveillance Engine endpoints (MJPEG streaming, snapshot, stats)
- HTTP 206 Partial Content media playback endpoints
- State transition actions
"""

from django.urls import path
from apps.core import views as core_views
from apps.core import api as api_views
from apps.accounts import views as auth_views
from apps.cameras import views as camera_views
from apps.recordings import views as recording_views
from apps.evidence import views as evidence_views
from apps.alerts import views as alert_views
from apps.notifications import views as notification_views

urlpatterns = [
    # React SPA Entrypoints (Root & Page Routes)
    path('', core_views.react_app_view, name='root'),
    path('dashboard/', core_views.react_app_view, name='dashboard'),
    path('cameras/', core_views.react_app_view, name='cameras'),
    path('cameras/<int:camera_id>/', core_views.react_app_view, name='camera_detail'),
    path('cameras/<int:camera_id>/preview/', core_views.react_app_view, name='camera_preview'),
    path('recordings/', core_views.react_app_view, name='recordings'),
    path('recordings/<int:recording_id>/', core_views.react_app_view, name='recording_detail'),
    path('evidence/', core_views.react_app_view, name='evidence'),
    path('evidence/<int:evidence_id>/', core_views.react_app_view, name='evidence_detail'),
    path('alerts/', core_views.react_app_view, name='alerts'),
    path('alerts/<int:alert_id>/', core_views.react_app_view, name='alert_detail'),
    path('cases/', core_views.react_app_view, name='cases'),
    path('cases/<int:case_id>/', core_views.react_app_view, name='case_detail'),
    path('notifications/', core_views.react_app_view, name='notifications'),
    path('login/', core_views.react_app_view, name='login'),
    path('signup/', core_views.react_app_view, name='signup'),
    path('forgot-password/', core_views.react_app_view, name='forgot_password'),
    path('reset-password/', core_views.react_app_view, name='reset_password'),
    path('help/', core_views.react_app_view, name='help'),
    path('profile/', core_views.react_app_view, name='profile'),

    # Auth REST APIs
    path('api/auth/csrf/', api_views.api_csrf, name='api_csrf'),
    path('api/auth/me/', api_views.api_me, name='api_me'),
    path('api/auth/login/', api_views.api_login, name='api_login'),
    path('api/auth/signup/', api_views.api_signup, name='api_signup'),
    path('api/auth/verify-otp/', api_views.api_verify_otp, name='api_verify_otp'),
    path('api/auth/resend-otp/', api_views.api_resend_otp, name='api_resend_otp'),
    path('api/auth/forgot-password/', api_views.api_forgot_password, name='api_forgot_password'),
    path('api/auth/reset-password/', api_views.api_reset_password, name='api_reset_password'),
    path('api/auth/logout/', api_views.api_logout, name='api_logout'),

    # Legacy HTML Auth compatibility routes (fallback)
    path('verify-email/', auth_views.verify_email_view, name='verify_email'),
    path('resend-otp/', auth_views.resend_otp_view, name='resend_otp'),
    path('verify-success/', auth_views.verify_success_view, name='verify_success'),
    path('resend-reset-otp/', auth_views.resend_reset_otp_view, name='resend_reset_otp'),
    path('logout/', auth_views.logout_view, name='logout'),

    # SOC Dashboard REST APIs
    path('api/dashboard/stats/', api_views.api_dashboard_stats, name='api_dashboard_stats'),

    # Camera REST & Streaming Endpoints
    path('api/cameras/', api_views.api_cameras_list, name='api_cameras_list'),
    path('api/cameras/<int:camera_id>/', api_views.api_camera_detail, name='api_camera_detail'),
    path('api/cameras/<int:camera_id>/test', camera_views.camera_test_view, name='camera_test'),
    path('api/cameras/<int:camera_id>/test/', camera_views.camera_test_view, name='camera_test_slash'),
    path('api/cameras/test-connection', camera_views.camera_test_connection_view, name='camera_test_connection'),
    path('api/cameras/test-connection/', camera_views.camera_test_connection_view, name='camera_test_connection_slash'),
    path('api/surveillance/health/', camera_views.surveillance_health_api_view, name='api_surveillance_health'),

    # Live Video MJPEG Streams (HTTP multipart MJPEG)
    path('cameras/<int:camera_id>/stream/', camera_views.camera_stream_view, name='camera_stream'),
    path('cameras/<int:camera_id>/stream/tracking/', camera_views.camera_stream_tracking_view, name='camera_stream_tracking'),
    path('cameras/<int:camera_id>/stream/original/', camera_views.camera_stream_original_view, name='camera_stream_original'),
    path('cameras/<int:camera_id>/stream/raw/', camera_views.camera_stream_original_view, name='camera_stream_raw'),
    path('cameras/<int:camera_id>/snapshot/', camera_views.camera_snapshot_view, name='camera_snapshot'),
    path('cameras/<int:camera_id>/stats/', camera_views.camera_stats_view, name='camera_stats'),
    path('cameras/<int:camera_id>/status/', camera_views.camera_stats_view, name='camera_status'),
    path('cameras/<int:camera_id>/status', camera_views.camera_stats_view, name='camera_status_no_slash'),
    path('cameras/<int:camera_id>/record/start', camera_views.camera_record_start_view, name='camera_record_start'),
    path('cameras/<int:camera_id>/record/start/', camera_views.camera_record_start_view, name='camera_record_start_slash'),
    path('cameras/<int:camera_id>/record/stop', camera_views.camera_record_stop_view, name='camera_record_stop'),
    path('cameras/<int:camera_id>/record/stop/', camera_views.camera_record_stop_view, name='camera_record_stop_slash'),
    path('cameras/<int:camera_id>/warm/', camera_views.camera_warm_view, name='camera_warm'),

    # Recordings REST APIs & HTTP 206 Partial Playback
    path('api/recordings/', api_views.api_recordings_list, name='api_recordings_list'),
    path('api/recordings/<int:recording_id>/', api_views.api_recording_detail, name='api_recording_detail'),
    path('recordings/<int:recording_id>/view/', recording_views.view_recording_media_view, name='recording_media'),
    path('recordings/<int:recording_id>/download/', recording_views.download_recording_view, name='recording_download'),

    # Evidence REST APIs & Media Preview
    path('api/evidence/', api_views.api_evidence_list, name='api_evidence_list'),
    path('api/evidence/<int:evidence_id>/', api_views.api_evidence_detail, name='api_evidence_detail'),
    path('evidence/<int:evidence_id>/preview/', evidence_views.preview_evidence_media_view, name='evidence_preview'),
    path('evidence/<int:evidence_id>/download/', evidence_views.download_evidence_view, name='evidence_download'),

    # Alerts & Cases REST APIs
    path('api/alerts/', api_views.api_alerts_list, name='api_alerts_list'),
    path('api/alerts/<int:alert_id>/', api_views.api_alert_detail, name='api_alert_detail'),
    path('api/alerts/<int:alert_id>/incident-context/', api_views.api_alert_incident_context, name='api_alert_incident_context'),
    path('api/alerts/<int:alert_id>/evidence/', api_views.api_alert_scoped_evidence, name='api_alert_scoped_evidence'),
    path('api/alerts/<int:alert_id>/recordings/', api_views.api_alert_scoped_recordings, name='api_alert_scoped_recordings'),
    path('api/alerts/<int:alert_id>/case/', api_views.api_alert_scoped_case, name='api_alert_scoped_case'),
    path('api/alerts/<int:alert_id>/create-case/', api_views.api_alert_create_case, name='api_alert_create_case'),
    path('api/alerts/<int:alert_id>/note/', api_views.api_alert_add_note, name='api_alert_add_note'),
    path('api/alerts/<int:alert_id>/notifications/', api_views.api_alert_scoped_notifications, name='api_alert_scoped_notifications'),
    path('api/alerts/<int:alert_id>/timeline/', api_views.api_alert_scoped_timeline, name='api_alert_scoped_timeline'),
    path('alerts/<int:alert_id>/acknowledge/', alert_views.alert_acknowledge_view, name='alert_acknowledge'),
    path('alerts/<int:alert_id>/resolve/', alert_views.alert_resolve_view, name='alert_resolve'),
    path('api/cases/', api_views.api_cases_list, name='api_cases_list'),
    path('api/cases/<int:case_id>/', api_views.api_case_detail, name='api_case_detail'),
    path('api/cases/<int:case_id>/note/', api_views.api_case_add_note, name='api_case_add_note'),

    # Notifications REST APIs
    path('api/notifications/', notification_views.api_notifications_list_view, name='api_notifications'),
    path('api/notifications', notification_views.api_notifications_list_view, name='api_notifications_no_slash'),
    path('api/notifications/unread-count/', notification_views.unread_count_api_view, name='api_unread_count'),
    path('notifications/<int:notification_id>/read/', notification_views.mark_notification_read_view, name='notification_read'),
    path('notifications/read-all/', notification_views.mark_all_notifications_read_view, name='notifications_read_all'),

    # Assistant & Health Endpoints
    path('api/assistant/chat/', core_views.assistant_chat_view, name='assistant_chat'),
    path('api/assistant/chat', core_views.assistant_chat_view, name='assistant_chat_no_slash'),
    path('health/', core_views.health_check_view, name='health'),
    path('api/health/', core_views.health_check_view, name='api_health'),
]
