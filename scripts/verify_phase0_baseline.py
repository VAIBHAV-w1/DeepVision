import shutil
import os
import sqlite3
import hashlib

os.makedirs('backup', exist_ok=True)
shutil.copy2('instance/deepvision.db', 'backup/deepvision_backup_phase0_master.db')
print('Database backed up successfully to backup/deepvision_backup_phase0_master.db')

conn = sqlite3.connect('instance/deepvision.db')
cursor = conn.cursor()
tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print(f'Total tables: {len(tables)}')
for t in tables:
    count = cursor.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
    print(f'  {t}: {count} rows')

# Check cameras
cameras = cursor.execute('SELECT id, name, source_type, source, is_active FROM cameras').fetchall()
print('\nCameras in DB:')
for c in cameras:
    print(f'  ID {c[0]}: {c[1]} | Type: {c[2]} | Source: {c[3]} | Active: {c[4]}')

# Check users
users = cursor.execute('SELECT id, full_name, email, role, is_active FROM users').fetchall()
print('\nUsers in DB:')
for u in users:
    print(f'  ID {u[0]}: {u[1]} ({u[2]}) | Role: {u[3]} | Active: {u[4]}')

# Check zones
zones = cursor.execute('SELECT id, camera_id, name, x1, y1, x2, y2, enabled FROM restricted_zones').fetchall()
print('\nRestricted Zones in DB:')
for z in zones:
    print(f'  ID {z[0]}: Camera {z[1]} | {z[2]} | Rect: ({z[3]},{z[4]}) to ({z[5]},{z[6]}) | Enabled: {z[7]}')


