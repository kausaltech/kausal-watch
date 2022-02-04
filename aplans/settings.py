"""
Django settings for aplans project.

Generated by 'django-admin startproject' using Django 2.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.1/ref/settings/
"""

import os

import environ
from corsheaders.defaults import default_headers as default_cors_headers  # noqa
from django.utils.translation import gettext_lazy as _

root = environ.Path(__file__) - 2  # two folders back
env = environ.FileAwareEnv(
    ENV_FILE=(str, ''),
    DEBUG=(bool, False),
    SECRET_KEY=(str, ''),
    ALLOWED_HOSTS=(list, []),
    EXTRA_INSTALLED_APPS=(list, []),
    CONFIGURE_LOGGING=(bool, False),
    DATABASE_URL=(str, 'sqlite:///db.sqlite3'),
    CACHE_URL=(str, 'locmemcache://'),
    MEDIA_ROOT=(environ.Path(), root('media')),
    STATIC_ROOT=(environ.Path(), root('static')),
    MEDIA_URL=(str, '/media/'),
    STATIC_URL=(str, '/static/'),
    SENTRY_DSN=(str, ''),
    COOKIE_PREFIX=(str, 'aplans'),
    SERVER_EMAIL=(str, 'noreply@ilmastovahti.fi'),
    DEFAULT_FROM_EMAIL=(str, 'noreply@ilmastovahti.fi'),
    INTERNAL_IPS=(list, []),
    OIDC_ISSUER_URL=(str, ''),
    OIDC_CLIENT_ID=(str, ''),
    OIDC_CLIENT_SECRET=(str, ''),
    AZURE_AD_CLIENT_ID=(str, ''),
    AZURE_AD_CLIENT_SECRET=(str, ''),
    MAILGUN_API_KEY=(str, ''),
    MAILGUN_SENDER_DOMAIN=(str, ''),
    MAILGUN_REGION=(str, ''),
    SENDGRID_API_KEY=(str, ''),
    HOSTNAME_PLAN_DOMAINS=(list, ['localhost']),
)

BASE_DIR = root()

if env('ENV_FILE'):
    environ.Env.read_env(env('ENV_FILE'))
elif os.path.exists(os.path.join(BASE_DIR, '.env')):
    environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

DEBUG = env('DEBUG')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
INTERNAL_IPS = env.list('INTERNAL_IPS',
                        default=(['127.0.0.1'] if DEBUG else []))
DATABASES = {
    'default': env.db()
}
DATABASES['default']['ATOMIC_REQUESTS'] = True

# Set type of implicit primary keys to AutoField. In newer versions of Django it is BigAutoField by default.
# https://docs.djangoproject.com/en/3.2/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

CACHES = {
    'default': env.cache(),
}

SECRET_KEY = env('SECRET_KEY')

SERVER_EMAIL = env('SERVER_EMAIL')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

SITE_ID = 1

# Logging
if env('CONFIGURE_LOGGING'):
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': True,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
            },
            'simple': {
                'format': '%(levelname)s %(name)s %(asctime)s %(message)s'
            },
        },
        'handlers': {
            'null': {
                'level': 'DEBUG',
                'class': 'logging.NullHandler',
            },
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'simple'
            },
        },
        'loggers': {
            'django.db': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            'django.template': {
                'handlers': ['null'],
                'level': 'WARNING',
                'propagate': False,
            },
            'django': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'raven': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False
            },
            'generic': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False,
            },
            'parso': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'requests': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'PIL': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            '': {
                'handlers': ['console'],
                'level': 'DEBUG',
                'propagate': False,
            }
        }
    }

# Application definition

INSTALLED_APPS = [
    'admin_numeric_filter',
    'admin_site.apps.AdminSiteConfig',
    'admin_site.apps.AdminSiteStatic',
    'dal',
    'dal_select2',
    'dal_admin_filters',

    'helusers.apps.HelusersConfig',
    # 'helusers.apps.HelusersAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'social_django',
    'django_extensions',
    'import_export',
    'anymail',
    'modeltrans',

    'wagtail.contrib.forms',
    'wagtail.contrib.redirects',
    'wagtail.embeds',
    'wagtail.sites',
    'wagtail.users',
    'wagtail.snippets',
    'documents',
    'wagtail.documents',
    'images',
    'wagtail.images',
    'wagtail.search',
    'wagtail.admin',
    'wagtail.core',
    'wagtail.contrib.modeladmin',
    'wagtail.contrib.postgres_search',
    'wagtailautocomplete',
    'wagtailfontawesome',
    'condensedinlinepanel',
    'generic_chooser',
    'wagtailorderable',
    'admin_list_controls',

    'modelcluster',
    'taggit',

    'admin_ordering',
    'ckeditor',
    'easy_thumbnails',
    'image_cropping',
    'reversion',

    'rest_framework',
    'rest_framework.authtoken',
    'django_filters',
    'grapple',
    'graphene_django',
]

INSTALLED_APPS += [
    'users',
    'actions',
    'indicators',
    'content',
    'people',
    'notifications',
    'pages',
    'feedback',
    'orgs',
]

EXTRA_INSTALLED_APPS: list[str] = env.list('EXTRA_INSTALLED_APPS')  # type:ignore
INSTALLED_APPS += EXTRA_INSTALLED_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'aplans.middleware.SocialAuthExceptionMiddleware',
    'aplans.middleware.AdminMiddleware',
]

ROOT_URLCONF = 'aplans.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'actions.context_processors.current_plan',
                'admin_site.context_processors.sentry',
                'wagtail.contrib.settings.context_processors.settings',
            ],
        },
    },
]

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'npm.finders.NpmFinder'
]
NPM_FILE_PATTERNS = {
    'ag-grid-community': [
        'dist/ag-grid-community.js', 'dist/ag-grid-community.noStyle.js',
        'dist/styles/ag-theme-alpine.css', 'dist/styles/ag-theme-material.css', 'dist/styles/ag-grid.css'
    ],
    'moment': [
        'dist/moment.js', 'dist/locale/*.js'
    ],
    '@sentry/browser': [
        'build/bundle.min.js*'
    ],
}

WSGI_APPLICATION = 'aplans.wsgi.application'

# Password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

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

# Authentication

# SOCIAL_AUTH_POSTGRES_JSONFIELD = True

AUTHENTICATION_BACKENDS = (
    'helusers.tunnistamo_oidc.TunnistamoOIDCAuth',
    'admin_site.backends.AzureADAuth',
    'django.contrib.auth.backends.ModelBackend',
)

AUTH_USER_MODEL = 'users.User'
LOGIN_REDIRECT_URL = '/admin/'
LOGOUT_REDIRECT_URL = '/admin/'

CSRF_COOKIE_NAME = '%s-csrftoken' % env.str('COOKIE_PREFIX')
SESSION_COOKIE_NAME = '%s-sessionid' % env.str('COOKIE_PREFIX')
LANGUAGE_COOKIE_NAME = '%s-language' % env.str('COOKIE_PREFIX')

TUNNISTAMO_BASE_URL = env.str('OIDC_ISSUER_URL')
SOCIAL_AUTH_TUNNISTAMO_KEY = env.str('OIDC_CLIENT_ID')
SOCIAL_AUTH_TUNNISTAMO_SECRET = env.str('OIDC_CLIENT_SECRET')
SOCIAL_AUTH_TUNNISTAMO_OIDC_ENDPOINT = TUNNISTAMO_BASE_URL + '/openid'

SOCIAL_AUTH_AZURE_AD_KEY = env.str('AZURE_AD_CLIENT_ID')
SOCIAL_AUTH_AZURE_AD_SECRET = env.str('AZURE_AD_CLIENT_SECRET')

SOCIAL_AUTH_PIPELINE = (
    'users.pipeline.log_login_attempt',

    # Get the information we can about the user and return it in a simple
    # format to create the user instance later. On some cases the details are
    # already part of the auth response from the provider, but sometimes this
    # could hit a provider API.
    'social_core.pipeline.social_auth.social_details',

    # Get the social uid from whichever service we're authing thru. The uid is
    # the unique identifier of the given user in the provider.
    'social_core.pipeline.social_auth.social_uid',

    # Reset logged-in user if UUID differs
    'helusers.pipeline.ensure_uuid_match',

    # Generate username from UUID
    'helusers.pipeline.get_username',

    # Checks if the current social-account is already associated in the site.
    'social_core.pipeline.social_auth.social_user',

    # Finds user by email address
    'users.pipeline.find_user_by_email',

    # Get or create the user and update user data
    'users.pipeline.create_or_update_user',

    # Create the record that associated the social account with this user.
    'social_core.pipeline.social_auth.associate_user',

    # Populate the extra_data field in the social record with the values
    # specified by settings (and the default ones like access_token, etc).
    'social_core.pipeline.social_auth.load_extra_data',

    # Update avatar photo from MS Graph
    'users.pipeline.update_avatar',

    # Store the end session URL in the user's session data so that
    # we can format logout links properly.
    'helusers.pipeline.store_end_session_url',
)

HELUSERS_PASSWORD_LOGIN_DISABLED = True

SESSION_SERIALIZER = 'django.contrib.sessions.serializers.PickleSerializer'

#
# REST Framework
#
REST_FRAMEWORK = {
    'PAGE_SIZE': 200,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PERMISSION_CLASSES': (
        'aplans.permissions.AnonReadOnly',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
}


CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_HEADERS = list(default_cors_headers) + [
    'sentry-trace',
    'x-cache-plan-identifier',
    'x-cache-plan-domain',
]

#
# GraphQL
#
GRAPHENE = {
    'SCHEMA': 'aplans.schema.schema',
    'MIDDLEWARE': [
        'aplans.graphene_views.APITokenMiddleware',
    ],
}

# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

LANGUAGES = (
    ('fi', _('Finnish')),
    ('en', _('English')),
    ('sv', _('Swedish')),
)
MODELTRANS_AVAILABLE_LANGUAGES = [x[0] for x in LANGUAGES]

LANGUAGE_CODE = 'en'

PARLER_LANGUAGES = {
    None: (
        {'code': 'fi'},
        {'code': 'en'},
        {'code': 'sv'},
    ),
    'default': {
        'fallbacks': ['en', 'fi', 'sv'],
        'hide_untranslated': False,   # the default; let .active_translations() return fallbacks too.
    }
}


TIME_ZONE = 'Europe/Helsinki'

USE_I18N = True

USE_L10N = True

USE_TZ = True

LOCALE_PATHS = [
    os.path.join(BASE_DIR, 'locale')
]

#
# Email
#
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
ANYMAIL = {}

if env.str('MAILGUN_API_KEY'):
    EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"
    ANYMAIL['MAILGUN_API_KEY'] = env.str('MAILGUN_API_KEY')
    ANYMAIL['MAILGUN_SENDER_DOMAIN'] = env.str('MAILGUN_SENDER_DOMAIN')
    if env.str('MAILGUN_REGION'):
        ANYMAIL['MAILGUN_API_URL'] = 'https://api.%s.mailgun.net/v3' % env.str('MAILGUN_REGION')

if env.str('SENDGRID_API_KEY'):
    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
    ANYMAIL['SENDGRID_API_KEY'] = env.str('SENDGRID_API_KEY')

# ckeditor for rich-text admin fields
CKEDITOR_CONFIGS = {
    'default': {
        'skin': 'moono-lisa',
        'toolbar_Basic': [
            ['Source', '-', 'Bold', 'Italic']
        ],
        'toolbar_Full': [
            ['Format', 'Bold', 'Italic', 'Underline', 'Strike', 'List', 'Undo', 'Redo'],
            ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-', 'Blockquote'],
            ['Link', 'Unlink'],
            ['HorizontalRule'],
            ['Source'],
        ],
        'removePlugins': 'uploadimage,uploadwidget',
        'extraPlugins': '',
        'toolbar': 'Full',
        'height': 300,
        'format_tags': 'p;h3;h4;h5;h6;pre'
    },
    'lite': {
        'skin': 'moono-lisa',
        'toolbar_Full': [
            ['Bold', 'Italic', 'Underline', 'Strike', 'List', 'Undo', 'Redo'],
            ['NumberedList', 'BulletedList', '-', 'Outdent', 'Indent', '-', 'Blockquote'],
            ['Link', 'Unlink'],
        ],
        'removePlugins': 'uploadimage,uploadwidget',
        'extraPlugins': '',
        'toolbar': 'Full',
        'height': 150,
    }
}

WAGTAILDOCS_DOCUMENT_MODEL = 'documents.AplansDocument'
WAGTAILIMAGES_IMAGE_MODEL = 'images.AplansImage'
WAGTAIL_SITE_NAME = 'Kausal Watch'
WAGTAIL_ENABLE_UPDATE_CHECK = False
WAGTAIL_PASSWORD_MANAGEMENT_ENABLED = True
WAGTAIL_EMAIL_MANAGEMENT_ENABLED = False
WAGTAIL_PASSWORD_RESET_ENABLED = True
WAGTAILADMIN_PERMITTED_LANGUAGES = list(LANGUAGES)
WAGTAILADMIN_USER_LOGIN_FORM = 'admin_site.forms.LoginForm'
WAGTAILSEARCH_BACKENDS = {
    'default': {
        'BACKEND': 'wagtail.contrib.postgres_search.backend',
    }
}


THUMBNAIL_PROCESSORS = (
    'easy_thumbnails.processors.colorspace',
    'images.processors.scale_and_crop',
    'easy_thumbnails.processors.filters',
)
IMAGE_CROPPING_JQUERY_URL = None
THUMBNAIL_HIGH_RESOLUTION = True


GRAPPLE = {
    'APPS': ['pages', 'documents', 'images'],
}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = env('STATIC_URL')
MEDIA_URL = env('MEDIA_URL')
STATIC_ROOT = env('STATIC_ROOT')
MEDIA_ROOT = env('MEDIA_ROOT')

# Reverse proxy stuff
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

SENTRY_DSN = env('SENTRY_DSN')

SILENCED_SYSTEM_CHECKS = [
    'fields.W904',  # postgres JSONField -> django JSONField
]

ENABLE_DEBUG_TOOLBAR = False


# local_settings.py can be used to override environment-specific settings
# like database and email that differ between development and production.
f = os.path.join(BASE_DIR, "local_settings.py")
if os.path.exists(f):
    import sys
    import types
    module_name = "%s.local_settings" % ROOT_URLCONF.split('.')[0]
    module = types.ModuleType(module_name)
    module.__file__ = f
    sys.modules[module_name] = module
    exec(open(f, "rb").read())

if not locals().get('SECRET_KEY', ''):
    secret_file = os.path.join(BASE_DIR, '.django_secret')
    try:
        SECRET_KEY = open(secret_file).read().strip()
    except IOError:
        import random
        system_random = random.SystemRandom()
        try:
            SECRET_KEY = ''.join([system_random.choice('abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)') for i in range(64)])  # noqa
            secret = open(secret_file, 'w')
            import os
            os.chmod(secret_file, 0o0600)
            secret.write(SECRET_KEY)
            secret.close()
        except IOError:
            Exception('Please create a %s file with random characters to generate your secret key!' % secret_file)

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=1.0,
        integrations=[DjangoIntegration()],
        environment='development' if DEBUG else 'production'
    )

if 'DATABASES' in locals():
    if DATABASES['default']['ENGINE'] in ('django.db.backends.postgresql', 'django.contrib.gis.db.backends.postgis'):
        DATABASES['default']['CONN_MAX_AGE'] = 600

if ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

HOSTNAME_PLAN_DOMAINS = env('HOSTNAME_PLAN_DOMAINS')
