import collections
from django.apps import AppConfig
from django.contrib.admin.filters import SimpleListFilter
from django.utils.translation import gettext_lazy as _
from functools import lru_cache


# FIXME: Monkey patch due to wagtail-admin-list-controls using a deprecated alias in collections package
# Wagtail uses the deprecated alias -- remove after updating to 2.16
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping

_wagtailsvg_get_unfiltered_object_list = None
_wagtailsvg_get_queryset = None
_wagtailsvg_list_filter = None
_wagtailsvg_get_edit_handler = None
_wagtail_get_base_snippet_action_menu_items = None


def _get_collections(request):
    plan = request.user.get_active_admin_plan()
    if plan.root_collection is None:
        return []
    return plan.root_collection.get_descendants(inclusive=True)


class CollectionFilter(SimpleListFilter):
    title = _('collection')
    parameter_name = 'collection'

    def lookups(self, request, model_admin):
        collections = _get_collections(request)
        return [(collection.id, str(collection)) for collection in collections]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(collection=self.value())


def get_unfiltered_object_list(self):
    collections = _get_collections(self.request)
    return self.model.objects.filter(collection__in=collections)


def get_queryset(self, request):
    from wagtailsvg.wagtail_hooks import SvgModelAdmin
    qs = super(SvgModelAdmin, self).get_queryset(request)
    collections = _get_collections(request)
    return qs.filter(collection__in=collections)


def get_edit_handler(self, *args, **kwargs):
    # If we import this on the top level, there will be an error that apps aren't loaded yet
    from wagtail.admin.panels import FieldPanel, ObjectList, TabbedInterface

    class CollectionFieldPanel(FieldPanel):
        def on_form_bound(self):
            super().on_form_bound()
            field = self.bound_field.field
            collections = _get_collections(self.request)
            field.queryset = field.queryset.filter(pk__in=collections)

    return TabbedInterface([
            ObjectList([
                CollectionFieldPanel('collection'),
                FieldPanel('title'),
                FieldPanel('file'),
                FieldPanel('tags'),
            ], heading="General"),
        ])


def monkeypatch_svg_chooser():
    from wagtailsvg.views import SvgModelChooserMixin
    from wagtailsvg.wagtail_hooks import SvgModelAdmin
    global _wagtailsvg_get_unfiltered_object_list
    global _wagtailsvg_get_queryset
    global _wagtailsvg_list_filter
    global _wagtailsvg_get_edit_handler

    if _wagtailsvg_get_unfiltered_object_list is None:
        _wagtailsvg_get_unfiltered_object_list = SvgModelChooserMixin.get_unfiltered_object_list
        SvgModelChooserMixin.get_unfiltered_object_list = get_unfiltered_object_list

    if _wagtailsvg_get_queryset is None:
        _wagtailsvg_get_queryset = SvgModelAdmin.get_queryset
        SvgModelAdmin.get_queryset = get_queryset

    if _wagtailsvg_list_filter is None:
        _wagtailsvg_list_filter = SvgModelAdmin.list_filter
        SvgModelAdmin.list_filter = (CollectionFilter,)

    if _wagtailsvg_get_edit_handler is None:
        _wagtailsvg_get_edit_handler = SvgModelAdmin.get_edit_handler
        SvgModelAdmin.get_edit_handler = get_edit_handler


@lru_cache(maxsize=None)
def get_base_snippet_action_menu_items(model):
    from actions.models.action import Action
    if model == Action:
        from wagtail.models import DraftStateMixin, LockableMixin, WorkflowMixin
        from wagtail.snippets.action_menu import (
            CancelWorkflowMenuItem, DeleteMenuItem, LockedMenuItem, RestartWorkflowMenuItem,  PublishMenuItem, SaveMenuItem,
            SubmitForModerationMenuItem, UnpublishMenuItem,
        )

        class PublishActionMenuItem(PublishMenuItem):
            def is_shown(self, context):
                user = context["request"].user
                return super().is_shown(context) and user.can_publish_action(context['instance'])

        class UnpublishActionMenuItem(UnpublishMenuItem):
            def is_shown(self, context):
                user = context["request"].user
                return super().is_shown(context) and user.can_publish_action(context['instance'])

        menu_items = [
            SaveMenuItem(order=0),
            DeleteMenuItem(order=10),
        ]
        if issubclass(model, DraftStateMixin):
            menu_items += [
                UnpublishActionMenuItem(order=20),
                PublishActionMenuItem(order=30),
            ]
        if issubclass(model, WorkflowMixin):
            menu_items += [
                CancelWorkflowMenuItem(order=40),
                RestartWorkflowMenuItem(order=50),
                SubmitForModerationMenuItem(order=60),
            ]
        if issubclass(model, LockableMixin):
            menu_items.append(LockedMenuItem(order=10000))

        return menu_items
    else:
        return _wagtail_get_base_snippet_action_menu_items(model)


def monkeypatch_snippet_action_menu():
    from wagtail.snippets import action_menu
    global _wagtail_get_base_snippet_action_menu_items

    if _wagtail_get_base_snippet_action_menu_items is None:
        _wagtail_get_base_snippet_action_menu_items = action_menu.get_base_snippet_action_menu_items
        action_menu.get_base_snippet_action_menu_items = get_base_snippet_action_menu_items


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = _('Actions')

    def ready(self):
        # monkeypatch filtering of Collections
        monkeypatch_svg_chooser()
        monkeypatch_snippet_action_menu()
        import actions.signals
