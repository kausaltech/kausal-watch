"""aplans URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import importlib
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from wagtail.admin import urls as wagtailadmin_urls
from wagtail.documents import urls as wagtaildocs_urls
from wagtailautocomplete.urls.admin import urlpatterns as autocomplete_admin_urls
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from .graphene_views import SentryGraphQLView
from .api_router import router as api_router
from actions.api import all_views as actions_api_views, all_routers as actions_api_routers
from actions.autocomplete import (
    ActionAutocomplete, CategoryAutocomplete, CommonCategoryTypeAutocomplete,
)
from admin_site.views import account, RootRedirectView, WadminRedirectView
from indicators.autocomplete import (
    QuantityAutocomplete, UnitAutocomplete, CommonIndicatorAutocomplete, IndicatorAutocomplete
)
from orgs.autocomplete import OrganizationAutocomplete
from people.autocomplete import PersonAutocomplete
from indicators.api import all_views as indicators_api_views
from insight.api import all_views as insight_api_views
from reports.autocomplete import ReportAutocomplete, ReportTypeAutocomplete, ReportTypeFieldAutocomplete
from users.views import change_admin_plan

extensions_api_views = []
if importlib.util.find_spec('kausal_watch_extensions') is not None:
    from kausal_watch_extensions.api import all_views
    extensions_api_views = all_views

for view in actions_api_views + indicators_api_views + insight_api_views + extensions_api_views:
    api_router.register(view['name'], view['class'], basename=view.get('basename'))

api_urls = []
for router in [api_router] + actions_api_routers:
    api_urls += router.urls

api_urlconf = [
    path('v1/', include(api_urls)),
]

urlpatterns = [
    re_path(r'^admin/change-admin-plan/(?:(?P<plan_id>\d+)/)?$', change_admin_plan, name='change-admin-plan'),
    *api_urlconf,
    path('v1/docs/', TemplateView.as_view(
        template_name='swagger-ui.html',
        extra_context={'schema_url': 'openapi-schema'}
    ), name='swagger-ui'),
    path('v1/schema/', SpectacularAPIView.as_view(urlconf=api_urlconf), name='schema'),
    # Optional UI:
    path('v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('v1/graphql/', csrf_exempt(SentryGraphQLView.as_view(graphiql=True)), name='graphql'),
    path('v1/graphql/docs/', TemplateView.as_view(
        template_name='graphql-voyager.html',
    ), name='graphql-voyager'),

    re_path(r'^admin/autocomplete/', include(autocomplete_admin_urls)),
    # FIXME: This overrides the URL in Wagtail's admin.urls/__init__.py to disable dark mode until we fix CSS issues
    re_path("^admin/account/", account, name="wagtailadmin_account"),
    re_path(r'^admin/', include(wagtailadmin_urls)),
    re_path(r'^wadmin', WadminRedirectView.as_view(), name='wadmin-redirect'),
    re_path(r'^documents/', include(wagtaildocs_urls)),
    # re_path(r'^pages/', include(wagtail_urls)),
    re_path(r'^org-autocomplete/$', OrganizationAutocomplete.as_view(), name='organization-autocomplete'),
    re_path(r'^action-autocomplete/$', ActionAutocomplete.as_view(), name='action-autocomplete'),
    re_path(r'^category-autocomplete/$', CategoryAutocomplete.as_view(), name='category-autocomplete'),
    re_path(r'^indicator-autocomplete/$', IndicatorAutocomplete.as_view(), name='indicator-autocomplete'),
    re_path(r'^quantity-autocomplete/$', QuantityAutocomplete.as_view(), name='quantity-autocomplete'),
    re_path(r'^report-autocomplete/$', ReportAutocomplete.as_view(), name='report-autocomplete'),
    re_path(r'^report-type-autocomplete/$', ReportTypeAutocomplete.as_view(), name='report-type-autocomplete'),
    re_path(r'^report-type-field-autocomplete/$', ReportTypeFieldAutocomplete.as_view(), name='report-type-field-autocomplete'),
    re_path(r'^unit-autocomplete/$', UnitAutocomplete.as_view(), name='unit-autocomplete'),
    re_path(
        r'^common-indicator-autocomplete/$',
        CommonIndicatorAutocomplete.as_view(),
        name='common-indicator-autocomplete'
    ),
    re_path(
        r'^commoncategorytype-autocomplete/$',
        CommonCategoryTypeAutocomplete.as_view(),
        name='commoncategorytype-autocomplete',
    ),
    re_path(r'^person-autocomplete/$', PersonAutocomplete.as_view(), name='person-autocomplete'),

    path('auth/', include('social_django.urls', namespace='social')),
    path('', include('admin_site.urls')),
    path('', RootRedirectView.as_view(), name='root-redirect'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar

    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]


handler500 = 'aplans.error_handling.server_error'
