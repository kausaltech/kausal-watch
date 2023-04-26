from django import forms
from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache

from actions.models import Action
from import_export.admin import ExportMixin, ImportExportMixin, ImportMixin
from import_export.resources import ModelResource
from indicators.models import Indicator
from reversion.admin import VersionAdmin

from .forms import AuthenticationForm

APP_ORDER = ['actions', 'indicators', 'content', 'people']


class AplansAdminSite(admin.AdminSite):
    index_template = 'aplans_admin/index.html'
    login_template = 'wagtailadmin/login.html'
    login_form = AuthenticationForm
    enable_nav_sidebar = False

    def _replace_translations(self):
        # These translations are here just so that they can be found by
        # makemessages and replaced with better ones.
        _("Add another %(model)s")
        _("Add another %(verbose_name)s")

    @property
    def site_header(self):
        if hasattr(settings, 'WAGTAIL_SITE_NAME'):
            site_name = settings.WAGTAIL_SITE_NAME
        else:
            return _("Django admin")
        return _("%(site_name)s admin") % {'site_name': site_name}

    def each_context(self, request):
        ret = super().each_context(request)
        ret['site_type'] = getattr(settings, 'SITE_TYPE', 'dev')
        ret['redirect_path'] = request.GET.get('next', None)
        ret['login_url'] = reverse('auth_login')
        ret['logout_url'] = reverse('auth_logout')

        if request.user.is_active:
            plan = request.user.get_active_admin_plan()
            if plan is not None:
                ret['site_header'] = plan.name
                ret['site_title'] = plan.name
                ret['site_url'] = plan.site_url
        return ret

    def get_app_list(self, request):
        app_list = super().get_app_list(request)
        first_apps = []
        for app_label in APP_ORDER:
            for app in app_list:
                if app['app_label'] == app_label:
                    first_apps.append(app)
                    app_list.remove(app)
                    break
        return first_apps + app_list

    @never_cache
    def logout(self, request, extra_context=None):
        if request.session and request.session.get('social_auth_end_session_url'):
            logout_url = reverse('auth_logout')
            return HttpResponseRedirect(logout_url)
        return super().logout(request, extra_context)

    @never_cache
    def login(self, request, extra_context=None):
        """
        Display the login form for the given HttpRequest.
        """
        if request.method == 'GET' and self.has_permission(request):
            # Already logged-in, redirect to admin index
            index_path = reverse('admin:index', current_app=self.name)
            return HttpResponseRedirect(index_path)

        from wagtail.admin.views.account import LoginView
        return LoginView.as_view()(request)


class AplansExportMixin(ExportMixin):
    # For import/export functionality
    def get_resource_kwargs(self, request, *args, **kwargs):
        out = super().get_resource_kwargs(request, *args, **kwargs)
        out['request'] = request
        return out


class AplansImportMixin(ImportMixin):
    def get_import_data_kwargs(self, request, *args, **kwargs):
        ret = super().get_import_data_kwargs(request, *args, **kwargs)
        ret['use_transactions'] = True
        return ret


class AplansImportExportMixin(AplansImportMixin, AplansExportMixin):
    import_export_change_list_template = ImportExportMixin.import_export_change_list_template

    def get_resource_kwargs(self, request, *args, **kwargs):
        out = AplansExportMixin.get_resource_kwargs(self, request, *args, **kwargs)
        out['request'] = request
        return out


class AplansResource(ModelResource):
    def __init__(self, request=None):
        self.request = request
        super().__init__()


class AplansModelAdmin(VersionAdmin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def media(self):
        media = super().media
        for jsl in media._js_lists:
            if 'admin/js/jquery.init.js' in jsl:
                jsl.remove('admin/js/jquery.init.js')
                break
        return media

    def _get_category_fields(self, plan, obj, with_initial=False):
        fields = {}
        if self.model == Action:
            filter_name = 'editable_for_actions'
        elif self.model == Indicator:
            filter_name = 'editable_for_indicators'
        else:
            raise Exception()

        for cat_type in plan.category_types.filter(**{filter_name: True}):
            qs = cat_type.categories.all()
            if obj and with_initial:
                initial = obj.categories.filter(type=cat_type)
            else:
                initial = None
            field = forms.ModelMultipleChoiceField(
                qs, label=cat_type.name, initial=initial, required=False,
            )
            field.category_type = cat_type
            fields['categories_%s' % cat_type.identifier] = field
        return fields

    class Media:
        # Aplans Admin UI customizations:
        # - Notify if the user is about to leave with unsaved changes.
        # - Set global jQuery
        js = (
            'admin_site/js/customizations.js',
        )


"""
class OrderableAdmin(OriginalOrderableAdmin):
    ordering_field = "sort_order"
    ordering_field_hide_input = False
    extra = 0
"""
