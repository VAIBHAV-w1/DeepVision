import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from root .env file
load_dotenv(BASE_DIR.parent / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dv-sec-prod-entropy-key-9f8a3c7e2b1d4f6a8e0c2b4d6f8a1c3e5b7d9f0a2c4e6b8d0f1a3c5e7b9d')
DEBUG = os.getenv('DJANGO_DEBUG', 'True').lower() in ('true', '1')

allowed_hosts_env = os.getenv('DJANGO_ALLOWED_HOSTS')
if allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_env.split(',') if h.strip()]
else:
    ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '0.0.0.0']

# Standard Django SMTP Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('MAIL_SERVER') or os.getenv('SMTP_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('MAIL_PORT') or os.getenv('SMTP_PORT', 587))
EMAIL_HOST_USER = os.getenv('MAIL_USERNAME') or os.getenv('SMTP_USERNAME', '')
EMAIL_HOST_PASSWORD = os.getenv('MAIL_PASSWORD') or os.getenv('SMTP_PASSWORD', '')
EMAIL_USE_TLS = (os.getenv('MAIL_USE_TLS') or os.getenv('SMTP_USE_TLS', 'True')).lower() == 'true'
EMAIL_USE_SSL = (os.getenv('MAIL_USE_SSL') or os.getenv('SMTP_USE_SSL', 'False')).lower() == 'true'
DEFAULT_FROM_EMAIL = os.getenv('MAIL_DEFAULT_SENDER') or os.getenv('SMTP_FROM') or EMAIL_HOST_USER

# Application definition - Phase 3 & 4 Web Layer
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'django.contrib.sessions',
    'django.contrib.messages',
    'apps.core',
    'apps.accounts',
    'apps.cameras',
    'apps.alerts',
    'apps.recordings',
    'apps.evidence',
    'apps.notifications',
    'apps.ai',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.accounts.middleware.AuthenticationMiddleware',
]

# Session Configuration: 100% Signed-Cookie based (ZERO database schema changes / tables)
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
SESSION_COOKIE_NAME = 'deepvision_django_session'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 86400 * 30  # 30 days
SESSION_COOKIE_SECURE = os.getenv('DJANGO_SECURE_COOKIES', 'False').lower() in ('true', '1')

# CSRF Configuration
CSRF_COOKIE_NAME = 'deepvision_django_csrftoken'
CSRF_COOKIE_HTTPONLY = False  # Allows standard client-side JS fetch headers
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = os.getenv('DJANGO_SECURE_COOKIES', 'False').lower() in ('true', '1')

csrf_trusted_origins_env = os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS')
if csrf_trusted_origins_env:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in csrf_trusted_origins_env.split(',') if o.strip()]
else:
    CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000', 'http://0.0.0.0:8000']

# Security Headers & Protections
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Messages Configuration: Cookie-based (ZERO database writes)
MESSAGE_STORAGE = 'django.contrib.messages.storage.cookie.CookieStorage'

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
                'apps.accounts.context_processors.auth_user',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database configuration: Pointing to existing DeepVision SQLite database in READ-ONLY mode
# DO NOT run migrations against existing tables.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR.parent / 'instance' / 'deepvision.db',
        'OPTIONS': {
            'timeout': 30.0,
        },
    }
}

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media paths (pointing to existing instance recordings and evidence)
MEDIA_ROOT = BASE_DIR.parent / 'instance'
MEDIA_URL = '/media/'

# Native Django Surveillance Subsystem Configuration
SURVEILLANCE_ARCHITECTURE = 'native_django'
YOLO_CONFIDENCE_THRESHOLD = 0.50
YOLO_INFERENCE_INTERVAL_MS = 150

# Logging Configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
