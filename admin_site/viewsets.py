from typing import Generic, Type, TypeVar

from django.db import models
from wagtail.snippets.views.snippets import CreateView, EditView, SnippetViewSet

from admin_site.forms import WatchAdminModelForm
from aplans.types import WatchAdminRequest

M = TypeVar('M', bound=models.Model)


class WatchEditView(EditView, Generic[M]):
    request: WatchAdminRequest
    model: Type[M]

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': self.request.user.get_active_admin_plan()
        }


class WatchCreateView(CreateView, Generic[M]):
    request: WatchAdminRequest
    model: Type[M]

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': self.request.user.get_active_admin_plan()
        }


class WatchViewSet(SnippetViewSet, Generic[M]):
    model: Type[M]
    add_view_class = WatchCreateView
    edit_view_class = WatchEditView

    def get_form_class(self, for_update: bool = False):
        if not self._edit_handler.base_form_class:
            self._edit_handler.base_form_class = WatchAdminModelForm
        return super().get_form_class(for_update)
