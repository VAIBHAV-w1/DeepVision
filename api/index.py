import os
import sys
from pathlib import Path

# Add project root and deepvision_django to sys.path
root_dir = Path(__file__).resolve().parent.parent
django_dir = root_dir / 'deepvision_django'

for p in [str(django_dir), str(root_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Never embed a production Django signing secret in source code.
if not os.environ.get('DJANGO_SECRET_KEY', '').strip():
    raise RuntimeError('DJANGO_SECRET_KEY must be configured as a protected production environment variable.')

from django.core.wsgi import get_wsgi_application

# Vercel looks for 'app' or 'handler'
app = get_wsgi_application()
