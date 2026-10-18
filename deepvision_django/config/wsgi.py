import os
import sys
from pathlib import Path
from django.core.wsgi import get_wsgi_application
from django.contrib.staticfiles.handlers import StaticFilesHandler

base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Wrap WSGI application with StaticFilesHandler to ensure React SPA static assets
# are served reliably even when DEBUG=False under production WSGI servers (Gunicorn/Waitress).
application = StaticFilesHandler(get_wsgi_application())
