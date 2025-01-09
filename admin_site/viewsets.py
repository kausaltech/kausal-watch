from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Model, ProtectedError
from django.forms.models import ModelForm
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from wagtail.admin import messages
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.snippets.views.snippets import CreateView, EditView, IndexView, SnippetViewSet

from aplans.utils import PlanRelatedModel

from admin_site.forms import WatchAdminModelForm
from admin_site.mixins import (
    ActivatePermissionHelperPlanContextMixin,
    ContinueEditingMixin,
    PlanRelatedViewMixin,
    SetInstanceMixin,
)
from admin_site.permissions import PlanRelatedPermissionPolicy
from admin_site.utils import admin_req
from admin_site.wagtail import execute_admin_post_save_tasks

if TYPE_CHECKING:
    from aplans.types import WatchAdminRequest


class WatchEditView[ModelT: Model, FormT: WagtailAdminModelForm](
    # PersistFiltersEditingMixin,  # TODO: Is this needed? Does not work right now.
    ContinueEditingMixin,
    PlanRelatedViewMixin,
    ActivatePermissionHelperPlanContextMixin,
    EditView[ModelT, FormT],
    SetInstanceMixin,
):
    object: ModelT
    model: type[ModelT]

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': admin_req(self.request).user.get_active_admin_plan(),
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

        execute_admin_post_save_tasks(form.instance, admin_req(self.request).user)
        return form_valid_return

    def get_error_message(self):
        if hasattr(self.object, 'verbose_name_partitive'):
            model_name = self.object.verbose_name_partitive
        else:
            model_name = self.object._meta.verbose_name

        return _("%s could not be created due to errors.") % capfirst(model_name)


class WatchCreateView[ModelT: Model, FormT: ModelForm](CreateView[ModelT, FormT]):
    request: WatchAdminRequest

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': self.request.user.get_active_admin_plan(),
        }

class WatchIndexView[ModelT: Model, FormT: ModelForm](
    ActivatePermissionHelperPlanContextMixin,
    IndexView,
):
    pass


class WatchViewSet[ModelT: Model, FormT: ModelForm](SnippetViewSet[ModelT, FormT]):
    index_view_class = WatchIndexView
    add_view_class = WatchCreateView
    edit_view_class = WatchEditView

    @property
    def permission_policy(self):
        if issubclass(self.model, PlanRelatedModel):
            return PlanRelatedPermissionPolicy(self.model)
        return super().permission_policy

    def get_form_class(self, for_update: bool = False):
        if self._edit_handler and not self._edit_handler.base_form_class:
            self._edit_handler.base_form_class = WatchAdminModelForm[ModelT]
        return super().get_form_class(for_update)
