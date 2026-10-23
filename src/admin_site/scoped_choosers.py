"""
Choosers that offer only what the user may see in the admin.

Chooser views look objects up in the model's default manager by default, so a plan admin could list or pick other
plans' objects through a chooser even where the admin listing hides them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wagtail.snippets.views.chooser import (
    ChooseResultsView,
    ChooseView,
    SnippetChooserViewSet,
    SnippetChosenMultipleView,
    SnippetChosenView,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import Model, QuerySet
    from django.http import HttpRequest

# The permissions Wagtail's listing views require one of
LISTING_PERMISSIONS = {'add', 'change', 'delete', 'view'}


def get_snippet_chooser_queryset(request: HttpRequest, model: type[Model]) -> QuerySet[Any]:
    """Return the objects of `model` that the snippet's admin listing shows to the user."""
    viewset = model.snippet_viewset  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    if not viewset.permission_policy.user_has_any_permission(request.user, LISTING_PERMISSIONS):
        return model._default_manager.none()
    queryset = viewset.get_queryset(request)
    if queryset is None:
        return model._default_manager.all()
    return queryset


class SnippetChooserQuerysetMixin:
    request: HttpRequest
    model_class: type[Model]

    def get_object_list(self) -> QuerySet[Any]:
        return get_snippet_chooser_queryset(self.request, self.model_class)


class PermissionScopedChooseView(SnippetChooserQuerysetMixin, ChooseView):
    pass


class PermissionScopedChooseResultsView(SnippetChooserQuerysetMixin, ChooseResultsView):
    pass


class PermissionScopedChosenView(SnippetChosenView):
    def get_object(self, pk: Any) -> Model:
        return get_snippet_chooser_queryset(self.request, self.model_class).get(pk=pk)


class PermissionScopedChosenMultipleView(SnippetChosenMultipleView):
    def get_objects(self, pks: Iterable[Any]) -> QuerySet[Any]:
        return get_snippet_chooser_queryset(self.request, self.model_class).filter(pk__in=pks)


class PermissionScopedSnippetChooserViewSet(SnippetChooserViewSet):
    choose_view_class = PermissionScopedChooseView
    choose_results_view_class = PermissionScopedChooseResultsView
    chosen_view_class = PermissionScopedChosenView
    chosen_multiple_view_class = PermissionScopedChosenMultipleView


class ChosenFromOfferedObjectsMixin[M: Model]:
    """
    Look up a chosen object only among the objects the chooser offers.

    `generic_chooser` looks the chosen object up in the model's default manager, so any object could be picked by
    its ID. Override `get_chosen_queryset()` where the offered objects depend on query parameters, as the chosen
    request doesn't carry them.
    """

    def get_chosen_queryset(self) -> QuerySet[M]:
        return self.get_unfiltered_object_list()  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def get_object(self, pk) -> M:
        return self.get_chosen_queryset().get(pk=pk)


class ChosenFromObjectListViewSetMixin:
    """
    Make a `kausal_common` chooser viewset look up chosen objects only among those in its `get_object_list()`.

    Wagtail's chosen views look objects up in the model's default manager, so any object could be picked by its ID.
    """

    @property
    def chosen_view(self):
        view_class = self.inject_view_methods(self.chosen_view_class, ['get_chosen_response_data', 'get_object'])  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        return self.construct_view(view_class)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def chosen_multiple_view(self):
        view_class = self.inject_view_methods(self.chosen_multiple_view_class, ['get_objects'])  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        return self.construct_view(view_class)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def get_object(self, view: Any, pk: Any) -> Model:
        return self.get_object_list(view).get(pk=pk)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]

    def get_objects(self, view: Any, pks: Iterable[Any]) -> QuerySet[Any]:
        return self.get_object_list(view).filter(pk__in=pks)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
