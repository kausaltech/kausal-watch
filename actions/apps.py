from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
from types import MethodType

# Horrible monkeypatch until helusers gives us a nice
# hook.
admin_site_each_context = None


def each_context(self, request):
    context = admin_site_each_context(request)
    if request.user.is_active:
        plan = request.user.get_active_admin_plan()
        if plan is not None:
            context['site_header'] = plan.name
    return context


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = _('Actions')

    def ready(self):
        from helusers.admin import site
        global admin_site_each_context

        if getattr(site, '_aplans_modified', False):
            return

        site.index_template = 'aplans_admin/index.html'
        admin_site_each_context = site.each_context
        site.each_context = MethodType(each_context, site)
        site._aplans_modified = True
