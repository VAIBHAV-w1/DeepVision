import os
import sys
import sqlite3

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.models import db

def init_database():
    """
    Initializes the database by creating all registered SQLAlchemy tables.
    Also dynamically migrates schemas for development sqlite database if columns are missing.
    This process is non-destructive and preserves existing data.
    """
    print("Starting database initialization...")
    
    # Create the app instance
    env = os.getenv("FLASK_ENV", "development")
    app = create_app(env)
    
    with app.app_context():
        # Ensure the instance directory exists if using SQLite
        db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        if db_uri.startswith("sqlite:///"):
            db_path = db_uri.replace("sqlite:///", "")
            db_path_abs = os.path.abspath(db_path)
            
            db_dir = os.path.dirname(db_path_abs)
            if not os.path.exists(db_dir):
                print(f"Creating instance directory: {db_dir}")
                os.makedirs(db_dir, exist_ok=True)
                
            # Create all tables first
            db.create_all()
            
            # Execute alter commands for dynamic schema updates in development SQLite
            if os.path.exists(db_path_abs):
                conn = sqlite3.connect(db_path_abs)
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(users)")
                columns = [col[1] for col in cursor.fetchall()]
                
                # Missing fields to add
                new_cols = [
                    ("email_otp_hash", "VARCHAR(255)"),
                    ("email_otp_expires_at", "DATETIME"),
                    ("email_otp_attempts", "INTEGER DEFAULT 0 NOT NULL"),
                    ("email_otp_sent_at", "DATETIME"),
                    ("password_reset_otp_hash", "VARCHAR(255)"),
                    ("password_reset_otp_expires_at", "DATETIME"),
                    ("password_reset_otp_attempts", "INTEGER DEFAULT 0 NOT NULL"),
                    ("password_reset_otp_sent_at", "DATETIME")
                ]
                
                for col_name, col_type in new_cols:
                    if col_name not in columns:
                        print(f"Adding column '{col_name}' ({col_type}) to table 'users'...")
                        cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                
                conn.commit()
                
                # Check for camera_groups and group_id in cameras
                cursor.execute("PRAGMA table_info(cameras)")
                cam_columns = [col[1] for col in cursor.fetchall()]
                if "group_id" not in cam_columns:
                    print("Adding column 'group_id' to table 'cameras'...")
                    # We must add group_id. SQLite does not fully support ADD COLUMN with FOREIGN KEY constraints 
                    # elegantly without table recreation, but for simple nullable columns, we can add it as INTEGER.
                    cursor.execute("ALTER TABLE cameras ADD COLUMN group_id INTEGER REFERENCES camera_groups(id) ON DELETE SET NULL")
                    conn.commit()
                
                if "preset_id" not in cam_columns:
                    print("Adding 'preset_id' column to 'cameras' table...")
                    cursor.execute("ALTER TABLE cameras ADD COLUMN preset_id INTEGER REFERENCES surveillance_presets(id) ON DELETE SET NULL")
                    conn.commit()
                
                # Check for response_state in alerts
                cursor.execute("PRAGMA table_info(alerts)")
                alert_columns = [col[1] for col in cursor.fetchall()]
                if "response_state" not in alert_columns:
                    print("Adding column 'response_state' to table 'alerts'...")
                    cursor.execute("ALTER TABLE alerts ADD COLUMN response_state VARCHAR(20) DEFAULT 'NEW'")
                    conn.commit()
                
                # Check for incident_notes
                conn.execute('''
        CREATE TABLE IF NOT EXISTS incident_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            body TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        ''')
                conn.commit()

                # Check for incident_cases
                conn.execute('''
        CREATE TABLE IF NOT EXISTS incident_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_number VARCHAR(50) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            alert_id INTEGER,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            priority VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            assigned_to VARCHAR(100),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE SET NULL
        )
        ''')
                conn.commit()
                
                # Check for incident_policies
                conn.execute('''
        CREATE TABLE IF NOT EXISTS incident_policies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            enabled BOOLEAN DEFAULT 1 NOT NULL,
            severity VARCHAR(20) NOT NULL,
            initial_response_minutes INTEGER NOT NULL,
            escalation_minutes INTEGER NOT NULL,
            resolution_minutes INTEGER NOT NULL,
            auto_escalate BOOLEAN DEFAULT 0 NOT NULL,
            auto_create_case BOOLEAN DEFAULT 0 NOT NULL,
            notify_on_escalation BOOLEAN DEFAULT 1 NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        ''')
                conn.commit()

                # Check for incident_playbooks
                conn.execute('''
        CREATE TABLE IF NOT EXISTS incident_playbooks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            enabled BOOLEAN DEFAULT 1 NOT NULL,
            priority INTEGER DEFAULT 10 NOT NULL,
            severity VARCHAR(20),
            event_type VARCHAR(50),
            camera_id INTEGER,
            group_id INTEGER,
            create_case BOOLEAN DEFAULT 0 NOT NULL,
            auto_escalate BOOLEAN DEFAULT 0 NOT NULL,
            send_notification BOOLEAN DEFAULT 0 NOT NULL,
            notification_severity VARCHAR(20),
            apply_sla_policy BOOLEAN DEFAULT 1 NOT NULL,
            cooldown_seconds INTEGER DEFAULT 0 NOT NULL,
            last_executed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE SET NULL,
            FOREIGN KEY (group_id) REFERENCES camera_groups(id) ON DELETE SET NULL
        )
        ''')
                conn.commit()
                
                conn.close()
                print("SQLite schema updates applied successfully!")

            # Verify alerts and restricted_zones tables exist
            conn2 = sqlite3.connect(db_path_abs)
            cursor2 = conn2.cursor()
            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'")
            if cursor2.fetchone():
                print("alerts table: EXISTS [OK]")
            else:
                print("alerts table: NOT FOUND (this is unexpected)")
            
            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='restricted_zones'")
            if cursor2.fetchone():
                print("restricted_zones table: EXISTS [OK]")
            else:
                print("restricted_zones table: NOT FOUND (this is unexpected)")

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evidence'")
            if cursor2.fetchone():
                print("evidence table: EXISTS [OK]")
            else:
                print("evidence table: NOT FOUND (this is unexpected)")

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'")
            if cursor2.fetchone():
                print("notifications table: EXISTS [OK]")
            else:
                print("notifications table: NOT FOUND (this is unexpected)")

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='recordings'")
            if cursor2.fetchone():
                print('recordings table: EXISTS [OK]')
            else:
                print('recordings table: NOT FOUND (this is unexpected)')
                
            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
            if cursor2.fetchone():
                print('audit_logs table: EXISTS [OK]')
            else:
                print('audit_logs table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='detection_profiles'")
            if cursor2.fetchone():
                print('detection_profiles table: EXISTS [OK]')
            else:
                print('detection_profiles table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_preferences'")
            if cursor2.fetchone():
                print('notification_preferences table: EXISTS [OK]')
            else:
                print('notification_preferences table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='camera_groups'")
            if cursor2.fetchone():
                print('camera_groups table: EXISTS [OK]')
            else:
                print('camera_groups table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incident_notes'")
            if cursor2.fetchone():
                print('incident_notes table: EXISTS [OK]')
            else:
                print('incident_notes table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incident_cases'")
            if cursor2.fetchone():
                print('incident_cases table: EXISTS [OK]')
            else:
                print('incident_cases table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incident_policies'")
            if cursor2.fetchone():
                print('incident_policies table: EXISTS [OK]')
            else:
                print('incident_policies table: NOT FOUND (this is unexpected)')

            cursor2.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='incident_playbooks'")
            if cursor2.fetchone():
                print('incident_playbooks table: EXISTS [OK]')
            else:
                print('incident_playbooks table: NOT FOUND (this is unexpected)')

            conn2.close()
        else:
            # For other databases, standard create_all()
            db.create_all()
            
    print("SQLAlchemy tables and columns verified successfully!")
        
if __name__ == "__main__":
    init_database()
    sys.exit(0)
