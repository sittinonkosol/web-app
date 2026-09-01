from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# ============================================================
# Load .env file if present (production: set env vars in shell/systemd)
# ============================================================
_env_file = BASE_DIR / '.env'
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

# ============================================================
# Core Security Settings
# ============================================================
SECRET_KEY = os.environ['SECRET_KEY']  # Raises KeyError if missing — intentional

DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')

# Parse comma-separated ALLOWED_HOSTS from env
_raw_hosts = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    'scquizz.apps.ScquizzConfig',
    'mcmanager.apps.McmanagerConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'scquizz.middleware.RateLimitMiddleware',  # Rate Limiting via Redis
    'core.middleware.RobotsHeaderMiddleware',  # X-Robots-Tag: noindex on all pages
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'core' / 'templates',
            BASE_DIR / 'scquizz' / 'template',
            BASE_DIR / 'another_project' / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'

# --- Redis Channel Layer (WebSocket) ---
_redis_host = os.environ.get('REDIS_HOST', '127.0.0.1')
_redis_port = int(os.environ.get('REDIS_PORT', '6379'))

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# --- Redis Cache (Rate Limiting + Session) ---
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{_redis_host}:{_redis_port}/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "TIMEOUT": 300,
    }
}

# --- PostgreSQL Database ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'webdc_db'),
        'USER': os.environ.get('DB_USER', 'webdc'),
        'PASSWORD': os.environ['DB_PASSWORD'],  # Raises KeyError if missing — intentional
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

import sys
if 'test' in sys.argv or 'test' in getattr(sys, '_called_from_test', []):
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
    CHANNEL_LAYERS['default'] = {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'scquizz' / 'template' / 'css',
    BASE_DIR / 'scquizz' / 'template' / 'js',
    BASE_DIR / 'scquizz' / 'template' / 'asset',
]

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# Allow LAN, Local & Cloudflare Tunnel network connections
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:80',
    'http://127.0.0.1:80',
    'http://192.168.0.250:8000',
    'http://100.68.29.111:8000',
    'https://*.trycloudflare.com',
    'https://*.cloudflare.com',
    'https://test.duckproject.in.th',
    'https://*.duckproject.in.th',
]

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# ============================================================
# Security Headers
# ============================================================
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Production-only security settings (skipped when DEBUG=True for local dev)
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True

    # HTTPS redirect — disabled here because Cloudflare/reverse proxy handles it.
    # Enabling this behind a proxy causes infinite redirect loops.
    SECURE_SSL_REDIRECT = False

    # HSTS: instruct browsers to only use HTTPS (1 year)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Secure cookies — only sent over HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    CSRF_COOKIE_SAMESITE = 'Lax'

# ============================================================
# Application Logging
# ============================================================
LOG_DIR = Path('/var/log/django-app')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'scquizz_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'scquizz.log'),
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'core': {
            'handlers': ['console', 'scquizz_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'scquizz': {
            'handlers': ['console', 'scquizz_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
