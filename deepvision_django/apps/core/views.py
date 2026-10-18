"""
Core Views for DeepVision Django Application.
Provides:
- Dashboard (real database statistics, camera cards, recent alerts)
- Help & Support documentation
- DeepVision Assistant API (grounded domain assistant)
- User Profile view
"""
import os
import json
from datetime import datetime, timezone
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import connection
from apps.accounts.decorators import login_required
from apps.cameras.models import Camera
from apps.alerts.models import Alert, IncidentCase
from apps.recordings.models import Recording
from apps.evidence.models import Evidence
from apps.notifications.models import Notification
from apps.core.chatbot_service import answer_query
from apps.ai.engine import get_engine_health


@login_required
def dashboard_view(request):
    """
    Renders the DeepVision SOC Dashboard with real SQLite database statistics.
    Camera video streaming remains on Flask; Django presents real DB records.
    """
    user_cameras = list(Camera.objects.all().order_by('id'))
    total_cameras = len(user_cameras)
    online_cameras = sum(1 for c in user_cameras if c.status == 'online')
    active_cameras = sum(1 for c in user_cameras if c.is_active)

    new_alerts_count = Alert.objects.filter(status__in=['new', 'unresolved', 'active', 'OPEN']).count()
    high_critical_count = Alert.objects.filter(severity__in=['high', 'critical', 'HIGH', 'CRITICAL']).count()
    total_recordings = Recording.objects.count()
    total_evidence = Evidence.objects.count()
    total_cases = IncidentCase.objects.count()
    unread_notifications = Notification.objects.filter(user_id=request.user.id, is_read=False).count()

    recent_alerts = list(Alert.objects.select_related('camera').order_by('-id')[:5])
    recent_recordings = list(Recording.objects.select_related('camera').order_by('-id')[:4])

    context = {
        'cameras': user_cameras,
        'user_cameras': user_cameras,
        'total_cameras': total_cameras,
        'online_cameras': online_cameras,
        'active_cameras': active_cameras,
        'new_alerts_count': new_alerts_count,
        'high_critical_count': high_critical_count,
        'total_recordings': total_recordings,
        'total_evidence': total_evidence,
        'total_cases': total_cases,
        'unread_notifications': unread_notifications,
        'recent_alerts': recent_alerts,
        'recent_recordings': recent_recordings,
    }
    return render(request, 'pages/dashboard/index.html', context)


@login_required
def help_view(request):
    """
    Renders the DeepVision Help & Documentation portal.
    """
    return render(request, 'pages/help/index.html')


@login_required
@require_http_methods(["POST"])
def assistant_chat_view(request):
    """
    API endpoint for DeepVision Assistant.
    Enforces deterministic, domain-grounded surveillance responses.
    """
    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        data = {}

    message = data.get("message", "").strip()
    if not message:
        return JsonResponse({"success": False, "error": "Message is required."}, status=400)

    reply = answer_query(message)
    return JsonResponse({"success": True, "reply": reply})


@login_required
def profile_view(request):
    """
    Renders user profile details.
    """
    return render(request, 'profile.html', {'user': request.user})


def health_check_view(request):
    """
    Django Application & System Health Endpoint.
    Checks:
    1. Django process liveness
    2. Database connectivity via real query execution (SELECT 1)
    3. Schema readiness (existence of required tables: users, cameras, alerts)
    4. Serverless environment persistence guarantees
    5. Canonical surveillance engine reachability & status
    """
    db_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
            db_ok = (row is not None and row[0] == 1)
    except Exception:
        db_ok = False

    db_vendor = getattr(connection, 'vendor', 'unknown')
    tables = []
    schema_ready = False
    required_core_tables = {'users', 'cameras', 'alerts'}

    if db_ok:
        try:
            tables = connection.introspection.table_names()
            schema_ready = required_core_tables.issubset(set(tables))
        except Exception:
            schema_ready = False

    # Detect serverless ephemeral SQLite fallback
    is_serverless = bool(os.getenv('VERCEL') or os.getenv('AWS_LAMBDA_FUNCTION_NAME'))
    db_name = str(connection.settings_dict.get('NAME') or '')
    is_ephemeral_sqlite = (db_vendor == 'sqlite' and (db_name == ':memory:' or not db_name))

    try:
        user_id = request.user.id if getattr(request, 'user', None) and request.user.is_authenticated else None
        engine_health = get_engine_health(user_id=user_id)
    except Exception as e:
        engine_health = {"status": "standby", "note": str(e)}

    # Diagnostic state resolution
    if not db_ok:
        overall_status = "unavailable"
        http_status = 503
        db_state = "disconnected"
        diagnostic = "Database connection failed. Service is unavailable."
    elif is_serverless and is_ephemeral_sqlite:
        overall_status = "pending_configuration"
        http_status = 503
        db_state = "pending_configuration"
        schema_ready = False
        diagnostic = "Serverless deployment requires persistent database configuration (DATABASE_URL). Ephemeral in-memory database cannot persist user records."
    elif not schema_ready:
        overall_status = "pending_migration"
        http_status = 503
        db_state = "connected"
        diagnostic = f"Database connected ({db_vendor}), but required tables are missing ({len(tables)} tables found). Schema migration required."
    elif engine_health.get("status") != "healthy":
        overall_status = "degraded"
        http_status = 200
        db_state = "connected"
        diagnostic = "Database connected and schema verified. Surveillance engine standby or degraded."
    else:
        overall_status = "healthy"
        http_status = 200
        db_state = "connected"
        diagnostic = "Database connected and schema verified."

    payload = {
        "status": overall_status,
        "django_app": "online",
        "database": db_state,
        "database_backend": db_vendor,
        "schema_ready": schema_ready,
        "tables_count": len(tables),
        "diagnostic": diagnostic,
        "surveillance_engine": engine_health.get("status", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JsonResponse(payload, status=http_status)


def react_app_view(request, *args, **kwargs):
    """
    Serves the production built React single-page application (SPA).
    All client-side routing is handled inside React.
    """
    from django.conf import settings
    from django.http import HttpResponse

    dist_index = settings.BASE_DIR / 'static' / 'dist' / 'index.html'
    if dist_index.exists():
        with open(dist_index, 'r', encoding='utf-8') as f:
            return HttpResponse(f.read(), content_type='text/html')

    # Fallback to templates/pages/dashboard/index.html if dist not yet built
    return dashboard_view(request)


