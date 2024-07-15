from typing import Generic, Type, TypeVar

from django.db import models
from django.db.models import ProtectedError
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from wagtail.admin import messages
from wagtail.snippets.views.snippets import CreateView, EditView, SnippetViewSet

from admin_site.forms import WatchAdminModelForm
from admin_site.mixins import (
    ActivatePermissionHelperPlanContextMixin, ContinueEditingMixin,
    PersistFiltersEditingMixin, PlanRelatedViewMixin, SetInstanceMixin
)
from admin_site.permissions import PlanRelatedPermissionPolicy
from admin_site.wagtail import execute_admin_post_save_tasks
from aplans.types import WatchAdminRequest
from aplans.utils import PlanRelatedModel

M = TypeVar('M', bound=models.Model)


class WatchEditView(
    PersistFiltersEditingMixin,
    ContinueEditingMixin,
    PlanRelatedViewMixin,
    ActivatePermissionHelperPlanContextMixin,
    EditView,
    SetInstanceMixin,
    Generic[M]
):
    request: WatchAdminRequest
    model: Type[M]

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': self.request.user.get_active_admin_plan()
        }

    def form_valid(self, form, *args, **kwargs):
        try:
            form_valid_return = super().form_valid(form, *args, **kwargs)
        except ProtectedError as e:
            for o in e.protected_objects:
                name = type(o)._meta.verbose_name_plural
                error = _("Error deleting items. Try first deleting any %(name)s that are in use.") % {'name': name}
                form.add_error(None, error)
                form.add_error(None, _('In use: "%(instance)s".') % {'instance': str(o)})
            messages.validation_error(self.request, self.get_error_message(), form)
            return self.render_to_response(self.get_context_data(form=form))

        execute_admin_post_save_tasks(form.instance, self.request.user)
        return form_valid_return

    def get_error_message(self):
        if hasattr(self.object, 'verbose_name_partitive'):
            model_name = self.object.verbose_name_partitive
        else:
            model_name = self.object._meta.verbose_name

        return _("%s could not be created due to errors.") % capfirst(model_name)


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

    @property
    def permission_policy(self):
        if issubclass(self.model, PlanRelatedModel):
            return PlanRelatedPermissionPolicy(self.model)
        return super().permission_policy

    def get_form_class(self, for_update: bool = False):
        if not self._edit_handler.base_form_class:
            self._edit_handler.base_form_class = WatchAdminModelForm
        return super().get_form_class(for_update)
