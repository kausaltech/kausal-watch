from django.utils.translation import ugettext_lazy as _
from helusers.admin_site import AdminSite as HelusersAdminSite


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
