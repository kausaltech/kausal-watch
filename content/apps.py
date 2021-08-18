from django.apps import AppConfig
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _


def create_site_general_content(sender, **kwargs):
    from .models import SiteGeneralContent

    plan = kwargs['instance']
    if SiteGeneralContent.objects.filter(plan=plan).exists():
        return

    obj = SiteGeneralContent(plan=plan)
    obj.site_title = plan.name
    obj.github_api_repository = 'https://github.com/kausaltech/kausal-watch'
    obj.github_ui_repository = 'https://github.com/kausaltech/kausal-watch-ui'
    obj.save()


class ContentConfig(AppConfig):
    name = 'content'
    verbose_name = _('Content')

    def ready(self):
        from actions.models import Plan
        post_save.connect(
            create_site_general_content, sender=Plan,
            dispatch_uid='create_site_general_content'
        )
