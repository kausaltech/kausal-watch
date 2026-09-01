from __future__ import annotations

from django.apps import AppConfig
from django.utils.translation import pgettext_lazy

_wagtail_image_chooser_viewset_permission_policy: object | None = None
_wagtail_get_base_snippet_action_menu_items: object | None = None
_create_deferring_forward_many_to_many_manager = None  # type: ignore[var-annotated]


def monkeypatch_image_chooser_viewset():
    from wagtail.images.views.chooser import ImageChooserViewSet

    from images.permissions import permission_policy

    global _wagtail_image_chooser_viewset_permission_policy  # noqa: PLW0603

    if _wagtail_image_chooser_viewset_permission_policy is None:
        _wagtail_image_chooser_viewset_permission_policy = ImageChooserViewSet.permission_policy
        ImageChooserViewSet.permission_policy = permission_policy


def monkeypatch_deferring_forward_many_to_many_manager():
    # This should be removed once https://github.com/wagtail/django-modelcluster/pull/203 is merged and taken into use
    import modelcluster.fields

    assert hasattr(modelcluster.fields, 'create_deferring_forward_many_to_many_manager')
    global _create_deferring_forward_many_to_many_manager  # noqa: PLW0603

    if _create_deferring_forward_many_to_many_manager is None:
        _create_deferring_forward_many_to_many_manager = (
            modelcluster.fields.create_deferring_forward_many_to_many_manager  # pyright:ignore[reportAttributeAccessIssue]
        )

    def patched_function(rel, original_manager_cls):  # noqa: ANN202
        assert _create_deferring_forward_many_to_many_manager is not None
        manager = _create_deferring_forward_many_to_many_manager(rel, original_manager_cls)

        def patched_method(self, queryset):  # noqa: ANN202
            return queryset._next_is_sticky().all()

        manager._apply_rel_filters = patched_method
        return manager

    modelcluster.fields.create_deferring_forward_many_to_many_manager = patched_function  # pyright:ignore[reportAttributeAccessIssue]


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = pgettext_lazy('Action model', 'Actions')

    def ready(self):
        # monkeypatch filtering of Collections
        monkeypatch_image_chooser_viewset()
        import actions.signals

        actions.signals.register_signal_handlers()
        monkeypatch_deferring_forward_many_to_many_manager()

        from actions.attribute_type_admin import check_attribute_value_models

        check_attribute_value_models()
