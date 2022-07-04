import collections
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


# FIXME: Monkey patch due to wagtail-admin-list-controls using a deprecated alias in collections package
# Wagtail uses the deprecated alias -- remove after updating to 2.16
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping

_wagtailsvg_get_unfiltered_object_list = None


def get_unfiltered_object_list(self):
    plan = self.request.user.get_active_admin_plan()
    if plan.root_collection is not None:
        collections = plan.root_collection.get_descendants(inclusive=True)
    else:
        collections = []
    return self.model.objects.filter(collection__in=collections)


def monkeypatch_svg_chooser():
    from wagtailsvg.views import SvgModelChooserMixin
    global _wagtailsvg_get_unfiltered_object_list

    if _wagtailsvg_get_unfiltered_object_list is not None:
        return

    _wagtailsvg_get_unfiltered_object_list = SvgModelChooserMixin.get_unfiltered_object_list
    SvgModelChooserMixin.get_unfiltered_object_list = get_unfiltered_object_list


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = _('Actions')

    def ready(self):
        # monkeypatch filtering of Collections
        monkeypatch_svg_chooser()
