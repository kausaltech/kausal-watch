from django import forms
from django.utils.translation import ugettext_lazy as _
from helusers.admin_site import AdminSite as HelusersAdminSite
from reversion.admin import VersionAdmin

from actions.models import Action
from indicators.models import Indicator


APP_ORDER = ['actions', 'indicators', 'content', 'people']


class AplansAdminSite(HelusersAdminSite):
    index_template = 'aplans_admin/index.html'

    def _replace_translations(self):
        # These translations are here just so that they can be found by
        # makemessages and replaced with better ones.
        _("Add another %(model)s")
        _("Add another %(verbose_name)s")

    def each_context(self, request):
        context = super().each_context(request)
        if request.user.is_active:
            plan = request.user.get_active_admin_plan()
            if plan is not None:
                context['site_header'] = plan.name
                context['site_title'] = plan.name
                context['site_url'] = plan.site_url
        return context

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


class AplansModelAdmin(VersionAdmin):
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
