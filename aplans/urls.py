from __future__ import annotations

import importlib.util
import typing
from urllib.parse import urlparse

from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView
from django.urls import include, path, re_path
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from django.views.i18n import JavaScriptCatalog
from wagtail.admin import urls as wagtailadmin_urls  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
from wagtail.admin.views.pages import search  # type: ignore[attr-defined]
from wagtail.documents import (
    urls as wagtaildocs_urls,  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
)

from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from wagtailautocomplete.urls.admin import urlpatterns as autocomplete_admin_urls

from kausal_common.admin_site.views import RootRedirectView
from kausal_common.datasets.api import all_routers as datasets_api_nested_routers, router as datasets_api_root_router
from kausal_common.deployment.health_check_view import health_view

from aplans.graphql_views import WatchGraphQLView

from actions.api import all_routers as actions_api_routers, all_views as actions_api_views
from actions.autocomplete import (
    ActionAutocomplete,
    CategoryAutocomplete,
    CommonCategoryTypeAutocomplete,
)
from actions.models import PlanDomain
from admin_site.views import WadminRedirectView
from admin_site.wagtail_hooks import restrict_chooser_pages_to_plan
from audit_logging.views import PlanScopedLogEntriesView
from indicators.api import all_views as indicators_api_views
from indicators.autocomplete import CommonIndicatorAutocomplete, IndicatorAutocomplete, QuantityAutocomplete, UnitAutocomplete
from insight.api import all_views as insight_api_views
from orgs.autocomplete import OrganizationAutocomplete
from people.autocomplete import PersonAutocomplete
from reports.autocomplete import ReportAutocomplete, ReportTypeAutocomplete, ReportTypeFieldAutocomplete
from reports.views import export_report_view
from users.views import change_admin_plan

from .api_router import router as api_router

if typing.TYPE_CHECKING:
    from types import ModuleType

    from django.contrib.contenttypes.models import ContentType
    from wagtail.query import PageQuerySet

extensions_api_views = []
kwe_urls: ModuleType | None = None
if importlib.util.find_spec('kausal_watch_extensions') is not None:
    from kausal_watch_extensions import urls
    from kausal_watch_extensions.api import all_views
    extensions_api_views = all_views
    kwe_urls = urls

for view in actions_api_views + indicators_api_views + insight_api_views + extensions_api_views:
    basename = view.get('basename') or api_router.get_default_basename(view['class'])
    if api_router.is_already_registered(basename):
        continue
    api_router.register(view['name'], view['class'], basename=view.get('basename'))


class KausalLogoutView(LogoutView):
    http_method_names = ["post", "options", "get"]

    def get(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def get_success_url_allowed_hosts(self):
        base = super().get_success_url_allowed_hosts()
        redirect_url = self.request.GET.get(self.redirect_field_name, '')
        if redirect_url:
            parsed = urlparse(redirect_url)
            configs = PlanDomain.objects.filter(hostname=parsed.hostname)
            if configs.exists():
                base.add(parsed.netloc)
            return base
        return base


class PageSearchView(search.SearchView):
    """Override Wagtail's SearchView in order to filter the search results by plan."""

    show_locale_labels: bool
    ordering: str
    selected_content_type: ContentType
    q: str

    def restrict_pages_to_plan(self, pages):
        # FIXME: We abuse restrict_chooser_pages_to_plan here, but we should ideally put its functionality somewhere
        # else.
        return restrict_chooser_pages_to_plan(pages, self.request)

    def annotate_queryset(self, queryset: PageQuerySet):
        queryset = self.restrict_pages_to_plan(queryset)
        self.all_pages = queryset
        return super().annotate_queryset(queryset)

for prefix, viewset, basename in datasets_api_root_router.registry:
    reg_base = basename or api_router.get_default_basename(viewset)
    if api_router.is_already_registered(reg_base):
        continue
    api_router.register(prefix, viewset, basename=basename)

api_urls = []
for router in [api_router] + actions_api_routers + datasets_api_nested_routers:
    api_urls += router.urls

api_urlconf = [
    path('v1/', include(api_urls)),
]

urlpatterns = [
    re_path(r'^admin/change-admin-plan/(?:(?P<plan_id>\d+)/)?$', change_admin_plan, name='change-admin-plan'),
    *api_urlconf,
    path("jsi18n/", JavaScriptCatalog.as_view(), name="javascript-catalog"),
    path('v1/docs/', TemplateView.as_view(
        template_name='swagger-ui.html',
        extra_context={'schema_url': 'openapi-schema'},
    ), name='swagger-ui'),
    path('v1/schema/', SpectacularAPIView.as_view(urlconf=api_urlconf), name='schema'),
    # Optional UI:
    path('v1/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('v1/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path('v1/graphql/', csrf_exempt(WatchGraphQLView.as_view()), name='graphql'),
    path('v1/graphql/docs/', TemplateView.as_view(
        template_name='graphql-voyager.html',
    ), name='graphql-voyager'),

    re_path(r'^admin/autocomplete/', include(autocomplete_admin_urls)),
    re_path(r'^admin/reports/site-history/$', PlanScopedLogEntriesView.as_view(), name="watch-plan-history"),
    re_path(
        r'^admin/reports/site-history/results/$',
        PlanScopedLogEntriesView.as_view(results_only=True), name="watch-plan-history-results"),
    # Hide default reporting URLs provided by Wagtail
    re_path(r'^admin/reports/.*', RootRedirectView.as_view(), name='disabled-reports'),
    # FIXME: This overrides the URLs in Wagtail's admin/urls/pages.py to allow filtering the queryset
    path("admin/pages/search/", PageSearchView.as_view(), name="search"),
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
        name='common-indicator-autocomplete',
    ),
    re_path(
        r'^commoncategorytype-autocomplete/$',
        CommonCategoryTypeAutocomplete.as_view(),
        name='commoncategorytype-autocomplete',
    ),
    re_path(r'^person-autocomplete/$', PersonAutocomplete.as_view(), name='person-autocomplete'),

    re_path('^report_export/(?:(?P<plan_identifier>[-a-z0-9]+)/)?$', export_report_view, name='action-report-export'),
    path('auth/', include('social_django.urls', namespace='social')),
    path("logout/", KausalLogoutView.as_view(), name="logout"),
    path('healthz/', csrf_exempt(health_view)),
    path('', include('admin_site.urls')),
    path('', RootRedirectView.as_view(), name='root-redirect'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    from django.contrib.staticfiles.views import serve as serve_static
    from django.db.transaction import non_atomic_requests

    from asgiref.sync import sync_to_async
    static_serve_view = non_atomic_requests(sync_to_async(serve_static))

    urlpatterns.append(re_path(r"^static/(?P<path>.*)$", static_serve_view))


if kwe_urls:
    urlpatterns.append(path('', include(kwe_urls)))


if settings.ENABLE_DEBUG_TOOLBAR:
    import debug_toolbar

    urlpatterns += [path('__debug__/', include(debug_toolbar.urls))]


handler500 = 'aplans.error_handling.server_error'
