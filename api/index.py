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

# Ensure Django secret key is present in serverless environment if not set
if not os.environ.get('DJANGO_SECRET_KEY'):
    os.environ['DJANGO_SECRET_KEY'] = 'dv-vercel-serverless-runtime-key-e7c8b9a1d2f34567890abcdef1234567'

from django.core.wsgi import get_wsgi_application

# Vercel looks for 'app' or 'handler'
app = get_wsgi_application()
