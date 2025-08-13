"""Django settings for Kausal Watch."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.utils.translation import gettext_lazy as _

import environ
from celery.schedules import crontab
from corsheaders.defaults import default_headers as default_cors_headers
from environ.environ import ImproperlyConfigured

from kausal_common import ENV_SCHEMA as COMMON_ENV_SCHEMA, register_settings as register_common_settings
from kausal_common.deployment import set_secret_file_vars
from kausal_common.sentry.init import init_sentry
from kausal_common.storage import storage_settings_from_s3_url

if TYPE_CHECKING:
    from urllib.parse import ParseResult


# TODO: Rename to `watch`. But then we need to also rename the `aplans` directory and references.
PROJECT_NAME = 'aplans'

root = environ.Path(__file__) - 2  # two folders back
env = environ.FileAwareEnv(
    ENV_FILE=(str, ''),
    DEBUG=(bool, False),
    DEPLOYMENT_TYPE=(str, 'development'),
    KUBERNETES_MODE=(bool, False),
    ENABLE_WAGTAIL_STYLEGUIDE=(bool, False),
    SECRET_KEY=(str, ''),
    ALLOWED_HOSTS=(list, []),
    CONFIGURE_LOGGING=(bool, True),
    DATABASE_URL=(str, 'sqlite:///db.sqlite3'),
    DATABASE_CONN_MAX_AGE=(int, 20),
    REDIS_URL=(str, ''),
    CACHE_URL=(str, 'locmemcache://'),
    MEDIA_ROOT=(environ.Path(), root('media')),
    STATIC_ROOT=(environ.Path(), root('static')),
    MEDIA_URL=(str, '/media/'),
    STATIC_URL=(str, '/static/'),
    SENTRY_DSN=(str, ''),
    COOKIE_PREFIX=(str, PROJECT_NAME),
    INTERNAL_IPS=(list, []),
    OIDC_ISSUER_URL=(str, ''),
    OIDC_CLIENT_ID=(str, ''),
    OIDC_CLIENT_SECRET=(str, ''),
    AZURE_AD_CLIENT_ID=(str, ''),
    AZURE_AD_CLIENT_SECRET=(str, ''),
    GOOGLE_CLIENT_ID=(str, ''),
    GOOGLE_CLIENT_SECRET=(str, ''),
    OKTA_CLIENT_ID=(str, ''),
    OKTA_CLIENT_SECRET=(str, ''),
    OKTA_API_URL=(str, ''),
    ADFS_CLIENT_ID=(str, ''),
    ADFS_CLIENT_SECRET=(str, ''),
    ADFS_API_URL=(str, ''),
    HOSTNAME_PLAN_DOMAINS=(list, ['localhost']),
    ELASTICSEARCH_URL=(str, ''),
    GOOGLE_MAPS_V3_APIKEY=(str, ''),
    ADMIN_BASE_URL=(str, 'http://localhost:8000'),
    LOG_SQL_QUERIES=(bool, False),
    LOG_GRAPHQL_QUERIES=(bool, False),
    LOG_PEOPLE_VERBOSE=(bool, True),
    LOG_DJANGO_RUNSERVER_MINIMIZE_NOISE=(bool, False),
    LOG_DJANGO_RUNSERVER_REQUESTS_MEDIA=(bool, True),
    LOG_DJANGO_RUNSERVER_REQUESTS_STATIC=(bool, True),
    LOG_DJANGO_RUNSERVER_REQUESTS_FAVICON=(bool, True),
    LOG_DJANGO_RUNSERVER_REQUESTS_BROKEN_PIPE=(bool, True),
    LOG_DJANGO_RUNSERVER_ERRORS_MEDIA=(bool, True),
    LOG_DJANGO_RUNSERVER_ERRORS_STATIC=(bool, True),
    LOG_DJANGO_RUNSERVER_ERRORS_FAVICON=(bool, True),
    S3_MEDIA_STORAGE_URL=(str, ''),
    REQUEST_LOG_MAX_DAYS=(int, 90),
    REQUEST_LOG_METHODS=(list, ['POST', 'PUT', 'PATCH', 'DELETE']),
    REQUEST_LOG_IGNORE_PATHS=(list, ['/v1/graphql/']),
    GITHUB_APP_ID=(str, ''),
    GITHUB_APP_PRIVATE_KEY=(str, ''),
    DEPLOY_ALLOWED_CNAMES_PRODUCTION=(list, []),
    DEPLOY_ALLOWED_CNAMES_PREVIEW=(list, []),
    DEPLOY_ALLOWED_CNAMES_DEVELOPMENT=(list, []),
    DEPLOY_TASK_GITOPS_REPO=(str, ''),
    MOUNTED_SECRET_PATHS=(list, []),
    ENABLE_DEBUG_TOOLBAR=(bool, False),
    KAUSAL_PATHS_URL=(str, ''),
    DISABLE_WAGTAIL_EDITING_SESSION_PING=(bool, False),
    **COMMON_ENV_SCHEMA,
)

BASE_DIR = root()

ENV_FILE = env.str('ENV_FILE', None)  # pyright: ignore[reportArgumentType]
if ENV_FILE:
    if not Path(ENV_FILE).exists():
        raise ImproperlyConfigured(f'File {ENV_FILE} specified in ENV_FILE does not exist')
    environ.Env.read_env(ENV_FILE)
else:
    dotenv_path = BASE_DIR / Path('.env')
    if dotenv_path.exists():
        environ.Env.read_env(dotenv_path)

# Read all files in the directories given in MOUNTED_SECRET_PATHS whose names look like environment variables and use
# the contents of the files for the corresponding variables
for directory in env('MOUNTED_SECRET_PATHS'):
    set_secret_file_vars(env, directory)

DEBUG = env('DEBUG')
DEPLOYMENT_TYPE = env('DEPLOYMENT_TYPE')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
INTERNAL_IPS = env.list('INTERNAL_IPS',
                        default=(['127.0.0.1'] if DEBUG else []))  # pyright: ignore
DATABASES = {
    'default': env.db_url(engine='kausal_common.database'),
}
DATABASES['default']['ATOMIC_REQUESTS'] = True

# Set type of implicit primary keys to AutoField. In newer versions of Django it is BigAutoField by default.
# https://docs.djangoproject.com/en/3.2/releases/3.2/#customizing-type-of-auto-created-primary-keys
DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# If Redis is configured, but no CACHE_URL is set in the environment,
# default to using Redis as the cache.
REDIS_URL = env('REDIS_URL')

cache_var = 'CACHE_URL'
if env.get_value('CACHE_URL', default=None) is None and REDIS_URL:  # pyright: ignore
    cache_var = 'REDIS_URL'
CACHES = {
    'default': env.cache_url(var=cache_var),
    'renditions': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'watch-renditions',
    },
}
if 'KEY_PREFIX' not in CACHES['default']:
    CACHES['default']['KEY_PREFIX'] = PROJECT_NAME

ELASTICSEARCH_URL = env('ELASTICSEARCH_URL')

SECRET_KEY = env('SECRET_KEY')

ADMIN_BASE_URL = env('ADMIN_BASE_URL')
WAGTAILADMIN_BASE_URL = ADMIN_BASE_URL
WAGTAILADMIN_COMMENTS_ENABLED = True

# Information needed to authenticate as a GitHub App
GITHUB_APP_ID = env('GITHUB_APP_ID')
GITHUB_APP_PRIVATE_KEY = env('GITHUB_APP_PRIVATE_KEY')

DEPLOY_ALLOWED_CNAMES_PRODUCTION = env('DEPLOY_ALLOWED_CNAMES_PRODUCTION')
DEPLOY_ALLOWED_CNAMES_PREVIEW = env('DEPLOY_ALLOWED_CNAMES_PREVIEW')
DEPLOY_ALLOWED_CNAMES_DEVELOPMENT = env('DEPLOY_ALLOWED_CNAMES_DEVELOPMENT')

DEPLOY_TASK_GITOPS_REPO = env('DEPLOY_TASK_GITOPS_REPO')

KAUSAL_PATHS_URL = env('KAUSAL_PATHS_URL')

SITE_ID = 1

# Application definition

INSTALLED_APPS = [
    'kausal_common',
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
    'wagtail_modeladmin',  # deprecated; https://docs.wagtail.org/en/stable/reference/contrib/modeladmin/migrating_to_snippets.html
    'wagtail_localize',
    'wagtail_localize.locales',  # replaces `wagtail.locales`
    'wagtailautocomplete',
    'generic_chooser',
    'wagtailorderable',
    'wagtailgeowidget',
    'wagtail_color_panel',

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
    'hijack',
]

if env('ENABLE_WAGTAIL_STYLEGUIDE'):
    INSTALLED_APPS += ['wagtail.contrib.styleguide']

INSTALLED_APPS += [
    'actions',
    'kausal_common.datasets',
    'content',
    'copying',
    'documentation',
    'feedback',
    'indicators',
    'notifications',
    'orgs',
    'pages',
    'people',
    'reports',
    'request_log',
    'users',
    'budget',
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
    f'{PROJECT_NAME}.middleware.SocialAuthExceptionMiddleware',
    f'{PROJECT_NAME}.middleware.RequestMiddleware',
    f'{PROJECT_NAME}.middleware.AdminMiddleware',
    'request_log.middleware.LogUnsafeRequestMiddleware',
    'hijack.middleware.HijackUserMiddleware',
]

ROOT_URLCONF = f'{PROJECT_NAME}.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / Path('templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'actions.context_processors.current_plan',
                'wagtail.contrib.settings.context_processors.settings',
                'admin_site.context_processors.sentry',
                'admin_site.context_processors.i18n',
            ],
        },
    },
]

WAGTAILADMIN_STATIC_FILE_VERSION_STRINGS = False

STORAGES: dict[str, dict[str, Any]] = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage',
    },
}

# If we're running under pytest, use InMemoryStorage. Otherwise, we check
# if the S3 backend is configured and use that instead.
if 'pytest' in sys.modules:
    STORAGES['default']['BACKEND'] = 'django.core.files.storage.InMemoryStorage'
else:
    media_storage_url: ParseResult = env.url('S3_MEDIA_STORAGE_URL')
    if media_storage_url.scheme:
        if media_storage_url.scheme != 's3':
            raise ImproperlyConfigured('S3_MEDIA_STORAGE_URL only supports s3 scheme')
        STORAGES['default'] = storage_settings_from_s3_url(media_storage_url, DEPLOYMENT_TYPE)

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

WSGI_APPLICATION = f'{PROJECT_NAME}.wsgi.application'

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
    'admin_site.backends.ADFSOpenIDConnectAuth',
    'django.contrib.auth.backends.ModelBackend',
    'social_core.backends.google_openidconnect.GoogleOpenIdConnect',
    'social_core.backends.okta_openidconnect.OktaOpenIdConnect',
)

AUTH_USER_MODEL = 'users.User'
LOGIN_URL = '/admin/login/'
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

SOCIAL_AUTH_GOOGLE_OPENIDCONNECT_KEY = env.str('GOOGLE_CLIENT_ID')
SOCIAL_AUTH_GOOGLE_OPENIDCONNECT_SECRET = env.str('GOOGLE_CLIENT_SECRET')

SOCIAL_AUTH_OKTA_OPENIDCONNECT_KEY = env.str('OKTA_CLIENT_ID')
SOCIAL_AUTH_OKTA_OPENIDCONNECT_SECRET = env.str('OKTA_CLIENT_SECRET')
SOCIAL_AUTH_OKTA_OPENIDCONNECT_API_URL = env.str('OKTA_API_URL')

SOCIAL_AUTH_ADFS_OPENIDCONNECT_KEY = env.str('ADFS_CLIENT_ID')
SOCIAL_AUTH_ADFS_OPENIDCONNECT_SECRET = env.str('ADFS_CLIENT_SECRET')
SOCIAL_AUTH_ADFS_OPENIDCONNECT_API_URL = env.str('ADFS_API_URL')

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
)

SESSION_SERIALIZER = 'django.contrib.sessions.serializers.JSONSerializer'

#
# REST Framework
#
REST_FRAMEWORK = {
    'PAGE_SIZE': 200,
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PERMISSION_CLASSES': (
        f'{PROJECT_NAME}.permissions.AnonReadOnly',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': f'{PROJECT_NAME}.openapi.AutoSchema',
}


CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = list(default_cors_headers) + [
    'sentry-trace',
    'x-cache-plan-identifier',
    'x-cache-plan-domain',
    'x-wildcard-domains',
]

#
# GraphQL
#
GRAPHENE = {
    'SCHEMA': f'{PROJECT_NAME}.schema.schema',
    'MIDDLEWARE': [
        f'{PROJECT_NAME}.graphene_views.APITokenMiddleware',
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
    ('el', _('Greek')),
    ('en', _('English (United States)')),
    ('en-AU', _('English (Australia)')),
    ('en-GB', _('English (United Kingdom)')),
    ('es', _('Spanish')),
    ('es-US', _('Spanish (United States)')),
    ('fi', _('Finnish')),
    ('lv', _('Latvian')),
    ('pt', _('Portuguese')),  # Use Brazilian Portuguese only for now
    ('pt-BR', _('Portuguese (Brazil)')),
    ('sv', _('Swedish')),
    ('sv-FI', _('Swedish (Finland)')),
)
# For languages that Django has no translations for, we need to manually specify what the language is called in that
# language. We use this for displaying the list of available languages in the user settings.
# If you forget to add something from LANGUAGES here, you will be reminded by an Exception when trying to access
# /wadmin/account/
LOCAL_LANGUAGE_NAMES = {
    'de-CH': "Deutsch (Schweiz)",
    'es-US': "español (Estados Unidos)",
    'sv-FI': "svenska (Finland)",
}
MODELTRANS_AVAILABLE_LANGUAGES = [x[0].lower() for x in LANGUAGES]
MODELTRANS_FALLBACK = {
    'default': (),
    'en-au': ('en',),
    'en-gb': ('en',),
    'de-ch': ('de',),
    'es-us': ('es',),
    'sv-fi': ('sv',),
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
    },
}

TIME_ZONE = 'Europe/Helsinki'

USE_I18N = True
WAGTAIL_I18N_ENABLED = True

USE_TZ = True

LOCALE_PATHS = [
    str(BASE_DIR / Path('locale')),
]

SPECTACULAR_SETTINGS = {
    'TITLE': 'Kausal Watch REST API',
    'DESCRIPTION': 'Monitor and manage action plans',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '^/v1',
    'SCHEMA_COERCE_PATH_PK_SUFFIX': True,
    'ENUM_NAME_OVERRIDES': {
        'OtherLanguagesEnum': LANGUAGES,
    },
}

# ckeditor for rich-text admin fields
CKEDITOR_CONFIGS = {
    'default': {
        'skin': 'moono-lisa',
        'toolbar_Basic': [
            ['Source', '-', 'Bold', 'Italic'],
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
        'format_tags': 'p;h3;h4;h5;h6;pre',
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
    },
}

WAGTAILDOCS_DOCUMENT_MODEL = 'documents.AplansDocument'
WAGTAILDOCS_SERVE_METHOD = 'serve_view'
WAGTAILIMAGES_IMAGE_MODEL = 'images.AplansImage'
WAGTAILIMAGES_EXTENSIONS = ['gif', 'jpg', 'jpeg', 'png', 'webp', 'svg']
WAGTAILEMBEDS_FINDERS = [
    {
        'class': 'wagtail.embeds.finders.oembed',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        'provider': 'Google Maps',
        'domain_whitelist': ('google.com/maps',),
        'title': 'Map',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        'provider': 'OpenStreetMap',
        'domain_whitelist': ('openstreetmap.org',),
        'title': 'Map',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        'provider': 'ArcGIS',
        'domain_whitelist': ('arcgis.com', 'maps.arcgis.com'),
        'title': 'Map',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        'provider': 'Plotly Chart Studio',
        'domain_whitelist': ('chart-studio.plotly.com',),
        'title': 'Chart',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        'provider': 'PowerBI',
        'domain_whitelist': ('app.powerbi.com',),
        'title': 'Chart',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        'provider': 'Sharepoint',
        'domain_whitelist': ('sharepoint.com', ),
        'title': 'Document',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        # If we leave the provider out, the "default" provider will be used
        'domain_whitelist': ('public.tableau.com', ),
        'title': 'Chart',
    },
    {
        'class': f'{PROJECT_NAME}.wagtail_embed_finders.GenericFinder',
        # If we leave the provider out, the "default" provider will be used
        'domain_whitelist': ('klimadashboard.de', ),
        'title': 'Chart',
    }

]
WAGTAIL_SITE_NAME = 'Kausal Watch'
WAGTAIL_ENABLE_UPDATE_CHECK = False
WAGTAIL_PASSWORD_MANAGEMENT_ENABLED = True
WAGTAIL_EMAIL_MANAGEMENT_ENABLED = False
WAGTAIL_PASSWORD_RESET_ENABLED = True
WAGTAILADMIN_PERMITTED_LANGUAGES = list(LANGUAGES)
WAGTAILADMIN_USER_LOGIN_FORM = 'admin_site.forms.LoginForm'
WAGTAILSEARCH_BACKENDS: dict[str, dict[str, Any]] = {
    # Will be overridden below if ELASTICSEARCH_URL is specified
    'default': {
        'BACKEND': 'wagtail.search.backends.database',
    },
}

if ELASTICSEARCH_URL:
    ANALYSIS_CONFIG: dict[str, dict[str, Any]] = {
        'fi': {
            'analyzer': {
                'default': {
                    'tokenizer': 'finnish',
                    'filter': ['lowercase', 'finnish_stop', 'raudikkoFilter'],
                },
             },
            'filter': {
                'raudikkoFilter': {
                    'type': 'raudikko',
                },
                'finnish_stop': {
                    'type': 'stop',
                    'stopwords': '_finnish',
                },
            },
        },
        'sv': {
            'analyzer': {
                'default': {
                    'type': 'swedish',
                },
            },
        },
        'da': {
            'analyzer': {
                'default': {
                    'type': 'danish',
                },
            },
        },
        'de': {
            'analyzer': {
                'default': {
                    'type': 'german',
                },
            },
        },
        'en': {
            'analyzer': {
                'default': {
                    'type': 'english',
                },
            },
        },
        'es': {
            'analyzer': {
                'default': {
                    'type': 'spanish',
                },
            },
        },
        'lv': {
            'analyzer': {
                'default': {
                    'type': 'latvian',
                },
            },
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
                    },
                },
            },
        }
    WAGTAILSEARCH_BACKENDS['default'] = WAGTAILSEARCH_BACKENDS['default-fi']


THUMBNAIL_PROCESSORS = (
    'easy_thumbnails.processors.colorspace',
    'images.processors.scale_and_crop',
    'easy_thumbnails.processors.filters',
)
IMAGE_CROPPING_JQUERY_URL: str | None = None
THUMBNAIL_HIGH_RESOLUTION = True

WAGTAIL_SLIM_SIDEBAR = False
WAGTAILADMIN_NOTIFICATION_INCLUDE_SUPERUSERS = False  # prevents adding superusers to workflow notification recipients

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

ENABLE_DEBUG_TOOLBAR = env('ENABLE_DEBUG_TOOLBAR')

# Show full SQL queries when running `runserver_plus` or `shell_plus` with `--print-sql`
SHELL_PLUS_PRINT_SQL_TRUNCATE: int | None = None
RUNSERVER_PLUS_PRINT_SQL_TRUNCATE: int | None = None


HOSTNAME_PLAN_DOMAINS = env('HOSTNAME_PLAN_DOMAINS')

GOOGLE_MAPS_V3_APIKEY = env('GOOGLE_MAPS_V3_APIKEY')

COMMON_CATEGORIES_COLLECTION = 'Common Categories'


# local_settings.py can be used to override environment-specific settings
# like database and email that differ between development and production.
local_settings = Path(BASE_DIR) / Path("local_settings.py")
if local_settings.exists():
    import types
    module_name = "%s.local_settings" % ROOT_URLCONF.split('.')[0]
    module = types.ModuleType(module_name)
    module.__file__ = str(local_settings)
    sys.modules[module_name] = module
    exec(local_settings.read_bytes())  # noqa: S102

if not locals().get('SECRET_KEY', ''):
    secret_file = Path(BASE_DIR) / Path('.django_secret')
    try:
        with secret_file.open() as f:
            SECRET_KEY = f.read().strip()
    except OSError:
        import random

        system_random = random.SystemRandom()
        try:
            SECRET_KEY = ''.join([system_random.choice('abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)') for i in range(64)])
            with secret_file.open('w') as f:
                secret_file.chmod(0o0600)
                f.write(SECRET_KEY)
        except OSError:
            raise ImproperlyConfigured(
                'Please create a %s file with random characters to generate your secret key!' % secret_file,
            ) from None


if DEBUG:  # noqa: SIM102
    if len(sys.argv) > 1 and 'runserver' in sys.argv[1]:
        try:
            from aplans.watchfiles_reloader import replace_reloader
            replace_reloader()
        except ImportError:
            pass


LOG_SQL_QUERIES = env('LOG_SQL_QUERIES') and DEBUG
LOG_GRAPHQL_QUERIES = env('LOG_GRAPHQL_QUERIES') and DEBUG


# Logging
LOGGING = None
if env('CONFIGURE_LOGGING'):
    from kausal_common.logging.init import LogFormat, UserLoggingOptions, init_logging_django

    is_kube = env.bool('KUBERNETES_MODE') or env.bool('KUBERNETES_LOGGING', False) # type: ignore
    log_format: LogFormat | None
    if not is_kube and DEBUG:
        # If logfmt hasn't been explicitly selected and DEBUG is on, fall back to autodetection.
        log_format = None
    else:
        log_format = 'logfmt'

    if DEBUG:
        runserver_logging = dict(
            django_runserver_minimize_noise=env('LOG_DJANGO_RUNSERVER_MINIMIZE_NOISE'),
            django_runserver_requests_media=env('LOG_DJANGO_RUNSERVER_REQUESTS_MEDIA'),
            django_runserver_requests_static=env('LOG_DJANGO_RUNSERVER_REQUESTS_STATIC'),
            django_runserver_requests_favicon=env('LOG_DJANGO_RUNSERVER_REQUESTS_FAVICON'),
            django_runserver_errors_media=env('LOG_DJANGO_RUNSERVER_ERRORS_MEDIA'),
            django_runserver_errors_static=env('LOG_DJANGO_RUNSERVER_ERRORS_STATIC'),
            django_runserver_errors_favicon=env('LOG_DJANGO_RUNSERVER_ERRORS_FAVICON'),
            django_runserver_requests_broken_pipe=env('LOG_DJANGO_RUNSERVER_REQUESTS_BROKEN_PIPE'),
            people_verbose=env('LOG_PEOPLE_VERBOSE'),
        )
    else:
        runserver_logging = dict()

    options = UserLoggingOptions(
        sql_queries=LOG_SQL_QUERIES,
        **runserver_logging,
    )
    LOGGING = init_logging_django(log_format, options=options)


REQUEST_LOG_MAX_DAYS = env('REQUEST_LOG_MAX_DAYS')
REQUEST_LOG_METHODS = env('REQUEST_LOG_METHODS')
REQUEST_LOG_IGNORE_PATHS = env('REQUEST_LOG_IGNORE_PATHS')
REQUEST_LOG_MAX_BODY_SIZE = 100 * 1024


if SENTRY_DSN:
    from kausal_common.sentry.init import init_sentry
    init_sentry(SENTRY_DSN, DEPLOYMENT_TYPE)


if DEBUG and ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')


if DEBUG:
    MIDDLEWARE.insert(
        0, f'{PROJECT_NAME}.middleware.PrintQueryCountMiddleware',
    )


if env('DISABLE_WAGTAIL_EDITING_SESSION_PING'):
    WAGTAIL_EDITING_SESSION_PING_INTERVAL = 0


if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    # TODO: Consider taking django-celery-results into use, as we have in KP
    CELERY_BROKER_URL = 'redis://localhost:6379'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379'

CELERY_BEAT_SCHEDULE = {
    'update-action-status': {
        'task': 'actions.tasks.update_action_status',
        'schedule': crontab(hour='4', minute='0'),
    },
    'calculate-indicators': {
        'task': 'indicators.tasks.calculate_indicators',
        'schedule': crontab(hour='23', minute='0'),
    },
    'send_daily_notifications': {
        'task': 'notifications.tasks.send_daily_notifications',
        'schedule': crontab(minute='0'),
    },
    'update-index': {
        'task': 'actions.tasks.update_index',
        'schedule': crontab(hour='3', minute='0'),
    },
}
# Required for Celery exporter: https://github.com/OvalMoney/celery-exporter
# For configuration, see also another exporter: https://github.com/danihodovic/celery-exporter
CELERY_WORKER_SEND_TASK_EVENTS = True
# CELERY_TASK_SEND_SENT_EVENT = True  # required only for danihodovic/celery-exporter


WAGTAIL_WORKFLOW_ENABLED = True
WAGTAILEMBEDS_RESPONSIVE_HTML = True

# Workaround until https://github.com/wagtail/wagtail/pull/11075 is merged
WAGTAILADMIN_RICH_TEXT_EDITORS = {
    'default': {
        "WIDGET": "admin_site.draftail_rich_text_area.DraftailRichTextAreaWithFixedTranslations",
    },
    'limited': {
        "WIDGET": "admin_site.draftail_rich_text_area.DraftailRichTextAreaWithFixedTranslations",
        "OPTIONS": {
            "features": ["bold", "italic", "ol", "ul", "link"],
        },
    },
    'very-limited-with-links': {
        "WIDGET": "admin_site.draftail_rich_text_area.DraftailRichTextAreaWithFixedTranslations",
        "OPTIONS": {
            "features": ["italic", "link"],
        },
    },
    'very-limited': {
        "WIDGET": "admin_site.draftail_rich_text_area.DraftailRichTextAreaWithFixedTranslations",
        "OPTIONS": {
            "features": ["bold", "italic"],
        },
    },
}

HIJACK_PERMISSION_CHECK = "admin_site.permissions.superusers_only_hijack"
HIJACK_INSERT_BEFORE: str | None = None

register_common_settings(locals())
# Put type hints for stuff registered in register_common_settings here because mypy doesn't figure it out
ALLOWED_SENDER_EMAILS: list[str]
DEFAULT_FROM_NAME: str

if importlib.util.find_spec('kausal_watch_extensions') is not None:
    INSTALLED_APPS.append('kausal_watch_extensions')
    from kausal_watch_extensions import register_settings
    register_settings(locals())
