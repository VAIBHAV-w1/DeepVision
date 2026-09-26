import os
import sys

sys.path.insert(0, "deepvision_django")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from django.contrib.sessions.backends.signed_cookies import SessionStore

s = SessionStore()
s['user_id'] = 2
s.save()
print(s.session_key)
