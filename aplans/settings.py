"""
Django settings for aplans project.

Generated by 'django-admin startproject' using Django 2.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.1/ref/settings/
"""

import os
import sys
import importlib
from celery.schedules import crontab
from typing import Literal

import environ
from corsheaders.defaults import default_headers as default_cors_headers  # noqa
from django.utils.translation import gettext_lazy as _

root = environ.Path(__file__) - 2  # two folders back
env = environ.FileAwareEnv(
    ENV_FILE=(str, ''),
    DEBUG=(bool, False),
    DEPLOYMENT_TYPE=(str, 'development'),
    SECRET_KEY=(str, ''),
    ALLOWED_HOSTS=(list, []),
    CONFIGURE_LOGGING=(bool, True),
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
    ELASTICSEARCH_URL=(str, ''),
    ADMIN_WILDCARD_DOMAIN=(str, ''),
    CELERY_BROKER_URL=(str, 'redis://localhost:6379'),
    CELERY_RESULT_BACKEND=(str, 'redis://localhost:6379'),
    GOOGLE_MAPS_V3_APIKEY=(str, ''),
    ADMIN_BASE_URL=(str, 'http://localhost:8000'),
    LOG_SQL_QUERIES=(bool, False),
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
    'renditions': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'watch-renditions',
    }
}

ELASTICSEARCH_URL = env('ELASTICSEARCH_URL')

SECRET_KEY = env('SECRET_KEY')

SERVER_EMAIL = env('SERVER_EMAIL')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

WAGTAILADMIN_BASE_URL = env('ADMIN_BASE_URL')
WAGTAILADMIN_COMMENTS_ENABLED = True

SITE_ID = 1

# Application definition

INSTALLED_APPS = [
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
    'corsheaders',

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
    'wagtail',
    'wagtailsvg',
    'wagtail.contrib.modeladmin',
    'wagtail_localize',
    'wagtail_localize.locales',  # replaces `wagtail.locales`
    'wagtailautocomplete',
    'wagtailfontawesome',
    'generic_chooser',
    'wagtailorderable',
    'admin_list_controls',
    'wagtailgeowidget',

    'modelcluster',
    'taggit',

    'easy_thumbnails',
    'reversion',

    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
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
    'feedback',
    'orgs',
    'pages',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
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

    # Generate username from UUID
    'users.pipeline.get_username',

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
    'DEFAULT_SCHEMA_CLASS': 'aplans.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Kausal Watch REST API',
    'DESCRIPTION': 'Monitor and manage action plans',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '^/v1',
    'SCHEMA_COERCE_PATH_PK_SUFFIX': True,
}


CORS_ALLOW_ALL_ORIGINS = True
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
    'DJANGO_CHOICE_FIELD_ENUM_V2_NAMING': True,
}

# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

# While Django seems to prefer lower-case regions in language codes (e.g., 'en-us' instead of 'en-US'; cf.
# https://github.com/django/django/blob/main/django/conf/global_settings.py), the Accept-Language header is
# case-insensitive, and Django also seems to be able to deal with upper case.
# https://docs.djangoproject.com/en/4.1/topics/i18n/#term-language-code
# On the other hand, i18next strongly suggests regions to be in upper case lest some features break.
# https://www.i18next.com/how-to/faq#how-should-the-language-codes-be-formatted
# Since we send the language code of a plan to the client, let's make sure we use the upper-case format everywhere in
# the backend already so we don't end up with different formats.
LANGUAGES = (
    ('da', _('Danish')),
    ('de', _('German')),
    ('de-CH', _('German (Switzerland)')),
    ('en', _('English (United States)')),
    ('en-GB', _('English (United Kingdom)')),
    ('en-AU', _('English (Australia)')),
    ('fi', _('Finnish')),
    ('sv', _('Swedish')),
)
# For languages that Django has no translations for, we need to manually specify what the language is called in that
# language. We use this for displaying the list of available languages in the user settings.
LOCAL_LANGUAGE_NAMES = {
    'de-CH': "Deutsch (Schweiz)",
}
MODELTRANS_AVAILABLE_LANGUAGES = [x[0].lower() for x in LANGUAGES]
MODELTRANS_FALLBACK = {
    'default': (),
    'en-au': ('en',),
    'en-gb': ('en',),
    'de-ch': ('de',),
}  # use language in default_language_field instead of a global fallback

WAGTAIL_CONTENT_LANGUAGES = LANGUAGES
WAGTAILSIMPLETRANSLATION_SYNC_PAGE_TREE = True

LANGUAGE_CODE = 'en'

PARLER_LANGUAGES = {
    None: (
        {'code': 'fi'},
        {'code': 'en'},
        {'code': 'sv'},
        {'code': 'de'},
        {'code': 'da'},
    ),
    'default': {
        'fallbacks': ['en', 'fi', 'sv', 'de', 'da'],
        'hide_untranslated': False,   # the default; let .active_translations() return fallbacks too.
    }
}


TIME_ZONE = 'Europe/Helsinki'

USE_I18N = True
WAGTAIL_I18N_ENABLED = True

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
    # Will be overridden below if ELASTICSEARCH_URL is specified
    'default': {
        'BACKEND': 'wagtail.search.backends.database',
    }
}

if ELASTICSEARCH_URL:
    ANALYSIS_CONFIG = {
        'fi': {
            'analyzer': {
                'default': {
                    'tokenizer': 'finnish',
                    'filter': ['lowercase', 'finnish_stop', 'raudikkoFilter']
                }
             },
            'filter': {
                'raudikkoFilter': {
                    'type': 'raudikko'
                },
                'finnish_stop': {
                    'type': 'stop',
                    'stopwords': '_finnish',
                }
            }
        },
        'sv': {
            'analyzer': {
                'default': {
                    'type': 'swedish'
                }
            }
        },
        'da': {
            'analyzer': {
                'default': {
                    'type': 'danish'
                }
            }
        },
        'de': {
            'analyzer': {
                'default': {
                    'type': 'german'
                }
            }
        },
        'en': {
            'analyzer': {
                'default': {
                    'type': 'english'
                }
            }
        },
    }
    for lang in ANALYSIS_CONFIG.keys():
        WAGTAILSEARCH_BACKENDS['default-%s' % lang] = {
            'BACKEND': 'search.backends',
            'URLS': [ELASTICSEARCH_URL],
            'INDEX': 'watch-%s' % lang,
            'TIMEOUT': 5,
            'LANGUAGE_CODE': lang,
            'INDEX_SETTINGS': {
                'settings': {
                    'index': {
                        'number_of_shards': 1,
                    },
                    'analysis': {
                        **ANALYSIS_CONFIG[lang],
                    }
                }
            }
        }
    WAGTAILSEARCH_BACKENDS['default'] = WAGTAILSEARCH_BACKENDS['default-fi']


THUMBNAIL_PROCESSORS = (
    'easy_thumbnails.processors.colorspace',
    'images.processors.scale_and_crop',
    'easy_thumbnails.processors.filters',
)
IMAGE_CROPPING_JQUERY_URL = None
THUMBNAIL_HIGH_RESOLUTION = True

WAGTAIL_SLIM_SIDEBAR = False
WAGTAIL_WORKFLOW_ENABLED = False

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

DEPLOYMENT_TYPE = env('DEPLOYMENT_TYPE')
SENTRY_DSN = env('SENTRY_DSN')

SILENCED_SYSTEM_CHECKS = [
    'fields.W904',  # postgres JSONField -> django JSONField
]

ENABLE_DEBUG_TOOLBAR = False

HOSTNAME_PLAN_DOMAINS = env('HOSTNAME_PLAN_DOMAINS')
ADMIN_WILDCARD_DOMAIN = env('ADMIN_WILDCARD_DOMAIN')

GOOGLE_MAPS_V3_APIKEY = env('GOOGLE_MAPS_V3_APIKEY')

COMMON_CATEGORIES_COLLECTION = 'Common Categories'


if importlib.util.find_spec('kausal_watch_extensions') is not None:
    INSTALLED_APPS.append('kausal_watch_extensions')

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


if DEBUG:
    if len(sys.argv) > 1 and 'runserver' in sys.argv[1]:
        try:
            from aplans.watchfiles_reloader import replace_reloader
            replace_reloader()
        except ImportError:
            pass

    from rich.traceback import install
    install()


# Logging
if env('CONFIGURE_LOGGING') and 'LOGGING' not in locals():
    def level(level: Literal['DEBUG', 'INFO', 'WARNING']):
        return dict(
            handlers=['rich' if DEBUG else 'console'],
            propagate=False,
            level=level,
        )

    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
            },
            'simple': {
                'format': '%(levelname)s %(name)s %(asctime)s %(message)s'
            },
            'rich': {
                'format': '%(message)s'
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
            'rich': {
                'level': 'DEBUG',
                'class': 'aplans.log_handler.LogHandler',
                'formatter': 'rich',
                'log_time_format': '%Y-%m-%d %H:%M:%S.%f'
            },
        },
        'loggers': {
            'django.db': level('DEBUG' if env('LOG_SQL_QUERIES') else 'INFO'),
            'django.template': level('WARNING'),
            'django.utils.autoreload': level('INFO'),
            'django': level('DEBUG'),
            'raven': level('WARNING'),
            'blib2to3': level('INFO'),
            'generic': level('DEBUG'),
            'parso': level('WARNING'),
            'requests': level('WARNING'),
            'urllib3.connectionpool': level('INFO'),
            'elasticsearch': level('WARNING'),
            'PIL': level('INFO'),
            'faker': level('INFO'),
            'factory': level('INFO'),
            'watchfiles': level('INFO'),
            'watchdog': level('INFO'),
            '': level('DEBUG'),
        }
    }


if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        send_default_pii=True,
        traces_sample_rate=1.0,
        integrations=[DjangoIntegration()],
        environment=DEPLOYMENT_TYPE,
    )

if 'DATABASES' in locals():
    if DATABASES['default']['ENGINE'] in ('django.db.backends.postgresql', 'django.contrib.gis.db.backends.postgis'):
        DATABASES['default']['CONN_MAX_AGE'] = 600

if ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
CELERY_BROKER_URL = env('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND')
NOTIFICATIONS_CRONTAB = {
    'helsinki-kierto': {'hour': 7, 'minute': 40},
    'lahti-ilmasto': {'hour': 8, 'minute': 10},
    'viitasaari-ilmasto': {'hour': 8, 'minute': 40},
}
CELERY_BEAT_SCHEDULE = {
    'update-action-status': {
        'task': 'actions.tasks.update_action_status',
        'schedule': crontab(hour=4, minute=0),
    },
    'calculate-indicators': {
        'task': 'indicators.tasks.calculate_indicators',
        'schedule': crontab(hour=23, minute=0),
    },
    **{f'send_notifications.{plan}': {
        'task': 'notifications.tasks.send_notifications',
        'schedule': crontab(**crontab_args),
        'kwargs': {
            'plan': plan,
        },
    } for plan, crontab_args in NOTIFICATIONS_CRONTAB.items()},
    'update-index': {
        'task': 'actions.tasks.update_index',
        'schedule': crontab(hour=3, minute=0),
    },
}
# Required for Celery exporter: https://github.com/OvalMoney/celery-exporter
# For configuration, see also another exporter: https://github.com/danihodovic/celery-exporter
CELERY_WORKER_SEND_TASK_EVENTS = True
# CELERY_TASK_SEND_SENT_EVENT = True  # required only for danihodovic/celery-exporter
