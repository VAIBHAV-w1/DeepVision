import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.abspath('deepvision_django'))
django.setup()

from django.db import connection

cursor = connection.cursor()
print("=== SAMPLE EVIDENCE ROWS ===")
cursor.execute("SELECT id, alert_id, camera_id, evidence_type, file_path, file_name, mime_type, file_size FROM evidence ORDER BY id DESC LIMIT 5;")
for row in cursor.fetchall():
    print(row)

print("\n=== EVIDENCE TYPES COUNT ===")
cursor.execute("SELECT evidence_type, COUNT(*) FROM evidence GROUP BY evidence_type;")
for row in cursor.fetchall():
    print(row)

print("\n=== SAMPLE RECORDINGS ROWS ===")
cursor.execute("SELECT id, camera_id, filename, file_path, duration_seconds, file_size, status FROM recordings ORDER BY id DESC LIMIT 5;")
for row in cursor.fetchall():
    print(row)

print("\n=== CHECKING IF RECORDING FILE_PATHS MATCH EVIDENCE FILE_PATHS ===")
cursor.execute("""
    SELECT r.id, r.file_path, e.id, e.alert_id, e.file_path 
    FROM recordings r 
    JOIN evidence e ON r.file_path = e.file_path 
    LIMIT 5;
""")
matches = cursor.fetchall()
print(f"Total matching paths: {len(matches)}")
for row in matches:
    print(row)

print("\n=== SAMPLE CASES ===")
cursor.execute("SELECT id, case_number, alert_id, title, priority, status FROM incident_cases ORDER BY id DESC LIMIT 5;")
for row in cursor.fetchall():
    print(row)

print("\n=== SAMPLE NOTIFICATIONS ===")
cursor.execute("SELECT id, alert_id, is_read, created_at FROM notifications ORDER BY id DESC LIMIT 5;")
for row in cursor.fetchall():
    print(row)
