"""
Independent Verification: Reconcile Dashboard Metrics with SQLite Database
Performs read-only SQLite queries and compares with /api/dashboard/stats/ response.
"""
import sqlite3
import urllib.request
import json
import http.cookiejar
import sys, os

# Setup session
sys.path.insert(0, "D:/DeepVision/deepvision_django")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django; django.setup()
from django.contrib.sessions.backends.signed_cookies import SessionStore

s = SessionStore()
s['user_id'] = 2
s.save()

cj = http.cookiejar.CookieJar()
cj.set_cookie(http.cookiejar.Cookie(
    0, 'deepvision_django_session', s.session_key, None, False,
    '127.0.0.1', False, False, '/', True, False, None, True, None, None, {}
))
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# 1. Fetch API stats
resp = opener.open("http://127.0.0.1:8000/api/dashboard/stats/")
api_data = json.loads(resp.read().decode())
print("API Dashboard Stats for User 2:")
for k, v in api_data.items():
    if not isinstance(v, (list, dict)):
        print(f"  API {k}: {v}")

# 2. Query Database directly (read-only)
conn = sqlite3.connect("D:/DeepVision/instance/deepvision.db")
c = conn.cursor()

c.execute("SELECT count(*) FROM alerts WHERE user_id = 2 AND status IN ('new', 'unresolved', 'active', 'OPEN')")
db_new_alerts = c.fetchone()[0]

c.execute("SELECT count(*) FROM alerts WHERE user_id = 2 AND severity IN ('high', 'critical', 'HIGH', 'CRITICAL')")
db_high_crit = c.fetchone()[0]

c.execute("SELECT count(*) FROM recordings WHERE user_id = 2")
db_recordings = c.fetchone()[0]

c.execute("SELECT count(*) FROM evidence WHERE user_id = 2")
db_evidence = c.fetchone()[0]

c.execute("SELECT count(*) FROM incident_cases WHERE user_id = 2")
db_cases = c.fetchone()[0]

c.execute("SELECT count(*) FROM notifications WHERE user_id = 2 AND is_read = 0")
db_unread_notifs = c.fetchone()[0]

conn.close()

print("\nDatabase Direct Counts for User 2:")
print(f"  DB new_alerts: {db_new_alerts}")
print(f"  DB high_critical: {db_high_crit}")
print(f"  DB recordings: {db_recordings}")
print(f"  DB evidence: {db_evidence}")
print(f"  DB cases: {db_cases}")
print(f"  DB unread_notifications: {db_unread_notifs}")

# 3. Reconcile
assert api_data.get('new_alerts_count') == db_new_alerts, f"Alerts mismatch: API {api_data.get('new_alerts_count')} vs DB {db_new_alerts}"
assert api_data.get('high_critical_count') == db_high_crit, f"High/Crit mismatch: API {api_data.get('high_critical_count')} vs DB {db_high_crit}"
assert api_data.get('total_recordings') == db_recordings, f"Recordings mismatch: API {api_data.get('total_recordings')} vs DB {db_recordings}"
assert api_data.get('total_evidence') == db_evidence, f"Evidence mismatch: API {api_data.get('total_evidence')} vs DB {db_evidence}"
assert api_data.get('total_cases') == db_cases, f"Cases mismatch: API {api_data.get('total_cases')} vs DB {db_cases}"
assert api_data.get('unread_notifications') == db_unread_notifs, f"Notifications mismatch: API {api_data.get('unread_notifications')} vs DB {db_unread_notifs}"

print("\nRECONCILIATION PASSED: 100% exact match between API stats and SQLite database records!")
