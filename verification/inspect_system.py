import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.abspath('deepvision_django'))
django.setup()

from django.apps import apps
from django.db import connection

print('=== ALL REGISTERED MODELS ===')
for model in apps.get_models():
    print(f"\nModel: {model.__name__} (app: {model._meta.app_label}, table: {model._meta.db_table})")
    for f in model._meta.get_fields():
        rel = ""
        if f.is_relation and f.related_model:
            rel = f" -> {f.related_model.__name__}"
        print(f"  - {f.name} ({f.get_internal_type() if hasattr(f, 'get_internal_type') else type(f).__name__}){rel}")

cursor = connection.cursor()
for table in ['alerts', 'evidence', 'recordings', 'incident_cases', 'incident_notes', 'notifications']:
    cursor.execute(f"PRAGMA table_info({table});")
    cols = cursor.fetchall()
    print(f"\nTABLE SCHEMA: {table}")
    for col in cols:
        print(f"  {col[1]} ({col[2]}) {'NOT NULL' if col[3] else 'NULL'} dflt={col[4]} pk={col[5]}")

    cursor.execute(f"SELECT COUNT(*) FROM {table};")
    count = cursor.fetchone()[0]
    print(f"  --> Total rows: {count}")
