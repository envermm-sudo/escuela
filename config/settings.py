import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = os.environ.get('DEBUG') == 'True'

ALLOWED_HOSTS = ['escuela.tsgestion.com.ar', '127.0.0.1', 'localhost']
CSRF_TRUSTED_ORIGINS = ['https://escuela.tsgestion.com.ar']

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'comunicacion',
    'staff',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'comunicacion.middleware.AdminSoloSuperuserMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates', BASE_DIR / 'comunicacion' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'comunicacion.context_processors.configuracion_portal',
                'staff.context_processors.staff_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=60,
    )
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

LANGUAGE_CODE = 'es-ar'

TIME_ZONE = 'America/Argentina/Buenos_Aires'

USE_I18N = True

USE_TZ = True

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

JAZZMIN_SETTINGS = {
    'site_title': 'Portal Escuela',
    'site_header': 'Portal Escuela',
    'site_brand': 'Comunicación',
    'welcome_sign': 'Bienvenido al panel de gestión',
    'copyright': 'Creado por Tecnosoft',
    'search_model': ['comunicacion.Comunicado', 'comunicacion.Galeria'],
    'show_sidebar': True,
    'navigation_expanded': False,
    'hide_apps': [],
    'hide_models': ['auth.user', 'auth.group'],
    'order_with_respect_to': [
        'comunicacion',
        'comunicacion.ConfiguracionPortal',
        'comunicacion.Grado',
        'comunicacion.Materia',
        'comunicacion.PerfilDocente',
        'comunicacion.AsignacionDocente',
        'comunicacion.HorarioDocente',
        'comunicacion.Comunicado',
        'comunicacion.Galeria',
        'comunicacion.PerfilPadre',
        'comunicacion.AuditLog',
        'auth',
    ],
    'icons': {
        'auth': 'fas fa-users-cog',
        'auth.user': 'fas fa-user',
        'auth.Group': 'fas fa-users',
        'comunicacion.ConfiguracionPortal': 'fas fa-cog',
        'comunicacion.Grado': 'fas fa-graduation-cap',
        'comunicacion.Materia': 'fas fa-book',
        'comunicacion.PerfilDocente': 'fas fa-chalkboard-teacher',
        'comunicacion.AsignacionDocente': 'fas fa-link',
        'comunicacion.Comunicado': 'fas fa-bullhorn',
        'comunicacion.Galeria': 'fas fa-images',
        'comunicacion.PerfilPadre': 'fas fa-user-friends',
        'comunicacion.AuditLog': 'fas fa-history',
        'comunicacion.HorarioDocente': 'fas fa-clock',
    },
    'default_icon_parents': 'fas fa-folder',
    'default_icon_children': 'fas fa-circle',
    'related_modal_active': True,
    'custom_css': 'comunicacion/css/admin_custom.css',
    'show_ui_builder': False,
    'changeform_format': 'horizontal_tabs',
    'changeform_format_overrides': {
        'comunicacion.ConfiguracionPortal': 'collapsible',
        'comunicacion.PerfilDocente': 'collapsible',
    },
}

JAZZMIN_UI_TWEAKS = {
    'navbar_small_text': False,
    'footer_small_text': True,
    'body_small_text': False,
    'brand_small_text': False,
    'brand_colour': 'navbar-indigo',
    'accent': 'accent-indigo',
    'navbar': 'navbar-white navbar-light',
    'no_navbar_border': True,
    'navbar_fixed': True,
    'layout_boxed': False,
    'footer_fixed': False,
    'sidebar_fixed': True,
    'sidebar': 'sidebar-light-indigo',
    'sidebar_nav_small_text': False,
    'sidebar_disable_expand': False,
    'sidebar_nav_child_indent': True,
    'sidebar_nav_compact_style': True,
    'sidebar_nav_legacy_style': False,
    'sidebar_nav_flat_style': False,
    'theme': 'default',
    'dark_mode_theme': None,
    'button_classes': {
        'primary': 'btn-primary',
        'secondary': 'btn-secondary',
        'info': 'btn-info',
        'warning': 'btn-warning',
        'danger': 'btn-danger',
        'success': 'btn-success',
    },
    'actions_sticky_top': True,
}

# ====================================================================
# Email (Gmail SMTP)
# ====================================================================
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'Portal Escolar <noreply@tsgestion.com.ar>')
SITE_URL = os.environ.get('SITE_URL', 'https://escuela.tsgestion.com.ar')

# Timeout corto para que la app no quede colgada si Gmail no responde
EMAIL_TIMEOUT = 15

# ====================================================================
# Uploads (imágenes pesadas de celular)
# ====================================================================
# Tamaño máximo de un POST completo (incluye archivos): 50 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50 MB
# Tamaño máximo en memoria por archivo individual antes de pasarlo a disco temporal: 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB
# Cantidad máxima de campos POST (incluye varios checkboxes de grados)
DATA_UPLOAD_MAX_NUMBER_FIELDS = 2000