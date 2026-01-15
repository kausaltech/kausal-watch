from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Model, ProtectedError
from django.forms.models import ModelForm
from django.urls import reverse
from django.utils.text import capfirst
from django.utils.translation import gettext as _, pgettext_lazy
from wagtail.admin import messages
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.admin.panels.field_panel import FieldPanel
from wagtail.models import Page
from wagtail.snippets.views.snippets import CreateView, DeleteView as SnippetDeleteView, EditView, IndexView, SnippetViewSet

from kausal_common.users import user_or_bust

from aplans.utils import PlanRelatedModel

from admin_site.forms import WatchAdminModelForm
from admin_site.mixins import (
    ActivatePermissionHelperPlanContextMixin,
    ContinueEditingMixin,
    PlanRelatedViewMixin,
)
from admin_site.permissions import PlanRelatedPermissionPolicy
from admin_site.utils import admin_req
from admin_site.wagtail import execute_admin_post_save_tasks

if TYPE_CHECKING:
    from django.http import HttpRequest

    from actions.models.action import BaseChangeLogMessage


class ObjectWithPublicChangeLogMessage(Protocol):
    def get_public_change_log_message(self) -> BaseChangeLogMessage | None: ...


class WatchEditView[ModelT: Model, FormT: WagtailAdminModelForm = WagtailAdminModelForm[Any]](
    # PersistFiltersEditingMixin,  # TODO: Is this needed? Does not work right now.
    ContinueEditingMixin,
    PlanRelatedViewMixin,
    ActivatePermissionHelperPlanContextMixin,
    EditView[ModelT, FormT],
    # SetInstanceMixin, # TODO: Is this needed? Causes linting errors right now.
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
            model_name = self.object.verbose_name_partitive  # type: ignore[attr-defined]
        else:
            model_name = self.object._meta.verbose_name

        return _("%s could not be created due to errors.") % capfirst(model_name)


class WatchCreateView[ModelT: Model, FormT: ModelForm[Any] = WagtailAdminModelForm](
    # PersistFiltersEditingMixin,  # TODO: Is this needed? Does not work right now.
    ContinueEditingMixin,
    PlanRelatedViewMixin,
    CreateView[ModelT, FormT],
    # SetInstanceMixin,  # TODO: Is this needed? Causes linting errors right now.
):
    request: HttpRequest

    def initialize_instance(self, request: HttpRequest, instance: ModelT) -> None:
        """
        Initialize the instance with plan defaults.

        Override this in subclasses to implement custom initialization logic.
        """
        if isinstance(instance, PlanRelatedModel):
            user = user_or_bust(request.user)
            plan = user.get_active_admin_plan()
            instance.initialize_plan_defaults(plan)

    def get_initial_form_instance(self):
        instance = super().get_initial_form_instance()
        if instance is None:
            instance = self.model()

        self.initialize_instance(self.request, instance)
        return instance

    def save_instance(self):
        instance = super().save_instance()

        if hasattr(instance, 'handle_admin_save'):
            instance.handle_admin_save(
                context={
                    'user': self.request.user,
                    'operation': 'create',
                },
            )

        return instance

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': user_or_bust(self.request.user).get_active_admin_plan(),
        }

class WatchIndexView[ModelT: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](
    ActivatePermissionHelperPlanContextMixin,
    IndexView[ModelT],
):
    pass


class WatchViewSet[ModelT: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](SnippetViewSet[ModelT, FormT]):
    index_view_class = WatchIndexView
    add_view_class = WatchCreateView  # type: ignore[assignment]
    edit_view_class = WatchEditView  # type: ignore[assignment]

    @property
    def permission_policy(self):
        if issubclass(self.model, PlanRelatedModel):
            return PlanRelatedPermissionPolicy(self.model)
        return super().permission_policy

    def get_form_class(self, for_update: bool = False):
        if self._edit_handler and not self._edit_handler.base_form_class:
            self._edit_handler.base_form_class = WatchAdminModelForm[ModelT]  # type: ignore[assignment]
        return super().get_form_class(for_update)


class BaseChangeLogMessageCreateView[M: models.Model, RelatedModel: ObjectWithPublicChangeLogMessage](WatchCreateView[M]):
    related_field_name: str
    success_url_name: str

    def get_related_id(self) -> str | None:
        """Get related object ID from GET params or POST data (hidden field)."""
        if self.request.method == 'POST':
            return self.request.POST.get(self.related_field_name)
        return self.request.GET.get(self.related_field_name)

    def get_related_object(self) -> RelatedModel | None:
        related_id = self.get_related_id()
        if not related_id:
            return None
        related_object = self.get_related_object_by_pk(related_id)
        return related_object

    def get_latest_change_log_message(self) -> BaseChangeLogMessage | None:
        related_object = self.get_related_object()
        if related_object is None:
            return None
        if isinstance(related_object, Page):
            related_object = related_object.get_specific()
        return related_object.get_public_change_log_message()

    def get_related_object_by_pk(self, _pk: str) -> RelatedModel | None:
        raise NotImplementedError

    def check_related_object_permission(self, _related_obj: RelatedModel | None) -> bool:
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        related_obj = self.get_related_object()
        if not self.check_related_object_permission(related_obj):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_page_subtitle(self):
        related_obj = self.get_related_object()
        if related_obj is not None:
            return pgettext_lazy('page subtitle', 'Change history message: %(obj)s') % {'obj': related_obj}
        return pgettext_lazy('page subtitle', 'Change history message')

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        related_obj = self.get_related_object()
        if related_obj is not None:
            setattr(form.instance, self.related_field_name, related_obj)
        form.instance.created_by = self.request.user  # type: ignore[attr-defined]
        return form

    def get_skip_url(self) -> str:
        return reverse(self.success_url_name)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['skip_url'] = self.get_skip_url()
        context['latest_change_log_message'] = self.get_latest_change_log_message()
        context['related_field_name'] = self.related_field_name
        context['related_id'] = self.get_related_id()
        return context

    def get_success_url(self):
        return reverse(self.success_url_name)


class BaseChangeLogMessageEditView[M: models.Model, RelatedModel: ObjectWithPublicChangeLogMessage](WatchEditView[M]):
    related_field_name: str
    success_url_name: str

    def check_related_object_permission(self, _related_obj: RelatedModel | None) -> bool:
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        related_obj = getattr(self.object, self.related_field_name, None)
        if not self.check_related_object_permission(related_obj):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        assert self.object is not None
        related_obj = getattr(self.object, self.related_field_name)
        return reverse(self.success_url_name, args=[related_obj.pk])


class BaseChangeLogMessageDeleteView[M: models.Model, RelatedModel: ObjectWithPublicChangeLogMessage](SnippetDeleteView):
    related_field_name: str

    def check_related_object_permission(self, _related_obj: RelatedModel | None) -> bool:
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        related_obj = getattr(self.object, self.related_field_name, None)
        if not self.check_related_object_permission(related_obj):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class BaseChangeLogMessageViewSet[M: models.Model](WatchViewSet[M]):
    add_to_admin_menu = False
    icon = 'doc-full'
    page_title = pgettext_lazy('page title', 'Add change history message')
    plan_filter_path: str
    create_template_name = 'aplans/change_log_message_create.html'

    panels = [
        FieldPanel('content'),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if qs is None:
            qs = self.model._default_manager.all()
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        return qs.filter(**{self.plan_filter_path: plan})
