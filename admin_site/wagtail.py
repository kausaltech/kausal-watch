from __future__ import annotations

from contextlib import contextmanager
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urljoin

import reversion
from django.conf import settings
from django.contrib.admin.utils import quote
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model, ProtectedError
from django.forms.models import ModelChoiceField, ModelForm
from django.http.request import QueryDict
from django.http.response import HttpResponseRedirect
from django.urls.base import reverse
from django.utils.decorators import method_decorator
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from modeltrans.translator import get_i18n_field
from reversion.revisions import add_to_revision, create_revision, set_comment, set_user
from wagtail.admin import messages
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.admin.panels import (
    InlinePanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.admin.panels.field_panel import FieldPanel

from wagtail_modeladmin.helpers.button import ButtonHelper
from wagtail_modeladmin.helpers.permission import PermissionHelper
from wagtail_modeladmin.options import ModelAdmin
from wagtail_modeladmin.views import CreateView, EditView, IndexView, InstanceSpecificView, ModelFormView, WMABaseView

from kausal_common.i18n.helpers import convert_language_code, get_language_from_default_language_field
from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import InstancesVisibleForMixin, PlanRelatedModel, append_query_parameter

from actions.models.plan import Plan

from .utils import FieldLabelRenderer, admin_req

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from django.http import HttpRequest
    from modeltrans.fields import TranslatedVirtualField
    from wagtail.admin.panels.base import Panel

    from wagtail_modeladmin.helpers.url import AdminURLHelper

    from kausal_common.datasets.models import DatasetScopeType

    from aplans.cache import PlanSpecificCache
    from aplans.types import WatchAdminRequest

    from actions.models import AttributeType
    from users.models import User

    class ViewMixinBase[M: Model](WMABaseView[M]):
        pass
else:
    class ViewMixinBase[M: Model]: ...


def insert_model_translation_panels[M: Model, PanelT: Panel[Any]](
    model: type[M],
    panels: Sequence[PanelT],
    request: HttpRequest,
    instance: Plan | AttributeType | None = None,
) -> list[PanelT]:
    """Return a list of panels containing all of `panels` and language-specific panels for fields with i18n."""
    i18n_field = get_i18n_field(model)
    if not i18n_field:
        return list(panels)

    out: list[PanelT] = []
    if instance is None:
        user = user_or_bust(request.user)
        instance = user.get_active_admin_plan()

    field_map: dict[str, dict[str | None, TranslatedVirtualField]] = {}
    for f in i18n_field.get_translated_fields():
        field_map.setdefault(f.original_name, {})[f.language] = f

    for p in panels:
        out.append(p)
        if not isinstance(p, FieldPanel):
            continue
        t_fields = field_map.get(p.field_name)
        if not t_fields:
            continue

        for lang_code in instance.other_languages:
            tf = t_fields.get(convert_language_code(lang_code, 'django'))
            if not tf:
                continue
            out.append(type(p)(tf.name))
    return out


def get_translation_tabs(
    instance: Model, request: HttpRequest, include_all_languages: bool = False, extra_panels=None
) -> list[Panel[Any]]:
    """
    Get tabs for entering translated strings.

    If `include_all_languages` is true, a tab is shown for each language that is not the default for the given instance.
    This default language is determined by the `default_language` argument of the model's i18n field. If there is no
    such argument, the global default language from `settings.LANGUAGE_CODE` is used.
    If `include_all_languages` is false, a tab is shown for each language supported by the currently active plan except,
    just like before, the default language of the instance.
    `extra_panels` maps a language code to a list of panels that should be put on the tab of that language.
    """
    if extra_panels is None:
        extra_panels = {}

    model = type(instance)
    i18n_field = get_i18n_field(model)
    if not i18n_field:
        return []
    tabs: list[Panel[Any]] = []

    user = user_or_bust(request.user)
    plan = user.get_active_admin_plan()

    languages_by_code = {x[0].lower(): x[1] for x in settings.LANGUAGES}
    if include_all_languages:
        languages = list(languages_by_code.keys())
    else:
        languages = [plan.primary_language_lowercase] + [lang.lower() for lang in plan.other_languages]

    # Omit default language because it's stored in the model field without a modeltrans language suffix
    default_language = get_language_from_default_language_field(instance, i18n_field)
    languages = [lang for lang in languages if lang != default_language]

    for lang_code in languages:
        assert lang_code == lang_code.lower()
        panels = []
        for field in i18n_field.get_translated_fields():
            if field.language != lang_code:
                continue
            panels.append(FieldPanel(field.name))
        panels += extra_panels.get(lang_code, [])
        tabs.append(ObjectList(panels, heading=languages_by_code[lang_code]))
    return tabs


# TODO: Reimplemented in admin_site/permissions.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class PlanRelatedModelAdminPermissionHelper[M: PlanRelatedModel](PermissionHelper[M]):
    check_admin_plan = True

    def disable_admin_plan_check(self):
        self.check_admin_plan = False

    def get_plans(self, obj: M) -> list[Plan]:
        if isinstance(obj, PlanRelatedModel):
            return obj.get_plans()
        raise NotImplementedError('implement in subclass')

    def _obj_matches_active_plan(self, user: User, obj: M) -> bool:
        if not self.check_admin_plan:
            return True

        obj_plans = self.get_plans(obj)
        active_plan = user.get_active_admin_plan()
        return any(obj_plan == active_plan for obj_plan in obj_plans)

    def user_can_inspect_obj(self, user: User, obj: M) -> bool:
        if not super().user_can_inspect_obj(user, obj):
            return False
        return self._obj_matches_active_plan(user, obj)

    def user_can_edit_obj(self, user: User, obj: M) -> bool:
        if not super().user_can_edit_obj(user, obj):
            return False
        return self._obj_matches_active_plan(user, obj)

    def user_can_delete_obj(self, user: User, obj: M) -> bool:
        if not super().user_can_edit_obj(user, obj):
            return False
        return self._obj_matches_active_plan(user, obj)


# TODO: Reimplemented in admin_site/permissions.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class PlanContextModelAdminPermissionHelper[M: Model](PermissionHelper[M]):
    plan: Plan | None

    def __init__(self, model, inspect_view_enabled=False):
        self.plan = None
        super().__init__(model, inspect_view_enabled)

    def prefetch_cache(self):
        """Prefetch plan-related content for permission checking."""
        pass

    def clean_cache(self):
        pass

    @contextmanager
    def activate_plan_context(self, plan: Plan):
        self.plan = plan
        self.prefetch_cache()
        try:
            yield
        finally:
            self.clean_cache()
            self.plan = None


class AdminOnlyPanel(ObjectList):
    pass


class AplansAdminModelForm[M: Model](WagtailAdminModelForm[M, 'User']):
    plan: Plan


if TYPE_CHECKING:
    BoundFieldPanelMixinBase = FieldPanel.BoundPanel
else:
    BoundFieldPanelMixinBase = object


class BoundPlanFilteredFieldPanelMixin(BoundFieldPanelMixinBase):
    """Mixin for bound panels to filter the related model queryset based on the active plan."""

    request: WatchAdminRequest

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        field = cast('ModelChoiceField[Any]', self.bound_field.field)
        queryset = field.queryset
        assert queryset is not None
        plan = self.request.get_active_admin_plan()
        related_model = queryset.model
        assert issubclass(related_model, PlanRelatedModel)
        field.queryset = related_model.filter_by_plan(plan, queryset)


class PlanFilteredFieldPanel[M: Model](FieldPanel[M]):
    class BoundPanel(BoundPlanFilteredFieldPanelMixin, FieldPanel.BoundPanel):
        pass


class BoundCustomizableBuiltInFieldPanelMixin(BoundFieldPanelMixinBase):
    """Mixin for bound panels for built-in fields to enable customizations by BuiltInFieldCustomization."""

    request: WatchAdminRequest

    def __init__(self, **kwargs):
        from admin_site.models import BuiltInFieldCustomization

        super().__init__(**kwargs)
        plan = self.request.get_active_admin_plan()
        is_public_field = True
        try:
            customization: BuiltInFieldCustomization = BuiltInFieldCustomization.objects.get(
                plan=plan,
                content_type=ContentType.objects.get_for_model(self.panel.model),
                field_name=self.field_name,
            )
        except BuiltInFieldCustomization.DoesNotExist:
            pass
        else:
            if customization.help_text_override:
                self.help_text = customization.help_text_override
            if customization.label_override:
                self.heading = customization.label_override
            if customization.instances_visible_for != InstancesVisibleForMixin.VisibleFor.PUBLIC:
                is_public_field = False
        self.heading = FieldLabelRenderer(plan)(self.heading, public=is_public_field)


class CustomizableBuiltInFieldPanel[M: Model](FieldPanel[M]):
    class BoundPanel(BoundCustomizableBuiltInFieldPanelMixin, FieldPanel.BoundPanel):
        pass


class CustomizableBuiltInPlanFilteredFieldPanel[M: Model](FieldPanel[M]):  # Ugh...
    class BoundPanel(BoundCustomizableBuiltInFieldPanelMixin, BoundPlanFilteredFieldPanelMixin, FieldPanel.BoundPanel):
        pass


if TYPE_CHECKING:

    class FieldPanelMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](FieldPanel[M, Any, FormT]):
        pass

    class TabbedInterfaceMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](TabbedInterface[M, FormT]):
        pass
else:

    class FieldPanelMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]]:
        pass

    class TabbedInterfaceMixinBase[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]]:
        pass

class BuiltInFieldCustomizationAwareEditHandlerMixin[M: Model, FormT: ModelForm[Any] = WagtailAdminModelForm[Any]](
    TabbedInterfaceMixinBase[M, FormT]
):
    """
    Mixin to make an edit handler take instances of BuiltInFieldCustomization into account.

    It will delete all fields from the edit handler's form that are not visible to the current user.
    """

    BoundPanel: Any

    def get_form_class(self):
        from admin_site.models import BuiltInFieldCustomization

        form_class = super().get_form_class()
        request = ctx_request.get()
        instance = ctx_instance.get()
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()

        def change_base_fields(form_class: type[WagtailAdminModelForm], model: type[Model]) -> None:
            customizations_qs = BuiltInFieldCustomization.objects.filter(
                plan=plan,
                content_type=ContentType.objects.get_for_model(model),
            )
            customizations: dict[str, BuiltInFieldCustomization] = {c.field_name: c for c in customizations_qs}
            for field_name in list(form_class.base_fields.keys()):
                customization = customizations.get(field_name)
                if customization:
                    if not customization.is_instance_visible_for(user, plan, instance):
                        del form_class.base_fields[field_name]
                        continue
                    if not customization.is_instance_editable_by(user, plan, instance):
                        form_class.base_fields[field_name].disabled = True
                        form_class.base_fields[field_name].required = False

        assert self.model is not None
        # Disable / remove built-in fields that are not editable / visible due to customization
        change_base_fields(form_class, self.model)
        for formset in form_class.formsets.values():
            change_base_fields(formset.form, formset.model)

        return form_class


def get_dataset_buttons(
    self: ButtonHelper,
    obj: DatasetScopeType | None,
    classnames_add: list[str] | None = None,
    classnames_exclude: list[str] | None = None,
    cache: PlanSpecificCache | None = None,
):
    buttons: list[dict[str, Any]] = []
    if classnames_add is None:
        classnames_add = []
    if find_spec('kausal_watch_extensions') is not None:
        from kausal_watch_extensions.dataset_editor import DatasetViewSet  # type: ignore[import-not-found]
    else:
        return buttons

    if obj is None:
        return buttons

    cache = cache or getattr(self.request, 'admin_cache')  # noqa: B009
    assert cache is not None
    schemas = cache.get_dataset_schemas_for_object(obj)
    for schema in schemas:
        dataset_cache = cache.datasets_by_scope_by_schema
        matching_dataset = (
            dataset_cache.get(
                self.model._meta.label,
                {},
            )
            .get(
                obj.pk,
                {},
            )
            .get(
                str(schema.uuid),
                None,
            )
        )
        classname = self.finalise_classname(
            classnames_add=classnames_add,
            classnames_exclude=classnames_exclude,
        )
        if matching_dataset:
            edit_url = reverse(DatasetViewSet().get_url_name('edit'), args=[matching_dataset.pk])
            label = _('Edit %(schema_name)s') % {'schema_name': schema.name}
            button = {
                'url': edit_url,
                'label': label,
                'classname': classname,
                'icon': 'edit',
            }
        else:
            add_url = reverse(DatasetViewSet().get_url_name('add'))
            add_url += f'?dataset_schema_uuid={schema.uuid}&model={self.model._meta.label}&object_id={obj.pk}'
            label = _('Add %(schema_name)s') % {'schema_name': schema.name}
            button = {
                'url': add_url,
                'label': label,
                'classname': classname,
                'icon': 'plus',
            }
        buttons.append(button)
    return buttons


class QueryParameterButtonHelper(ButtonHelper):
    """
    Button helper that preserves a query parameter across admin view URLs.

    Subclasses must set ``parameter_name`` to the GET parameter to preserve
    (e.g., ``'content_type'``, ``'category_type'``).
    """

    parameter_name: str

    def add_button(self, *args, **kwargs):
        """Only show the "add" button when the query parameter is present."""
        if self.parameter_name not in self.request.GET:
            return None
        data = super().add_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], self.parameter_name)
        return data

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], self.parameter_name)
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], self.parameter_name)
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], self.parameter_name)
        return data


class AplansButtonHelper(ButtonHelper):
    request: HttpRequest
    edit_button_classnames = ['button-primary']

    def edit_button(self, pk, classnames_add=None, classnames_exclude=None):
        button = super().edit_button(pk, classnames_add, classnames_exclude)
        return {
            **button,
            'icon': 'edit',
        }

    def view_live_button(self, obj, classnames_add=None, classnames_exclude=None):
        if obj is None or not hasattr(obj, 'get_view_url'):
            return None
        request = admin_req(self.request)
        if isinstance(obj, Plan):
            url = obj.get_view_url(request=request)
        else:
            user = user_or_bust(self.request.user)
            url = obj.get_view_url(plan=user.get_active_admin_plan(), request=request)
        if not url:
            return None

        classnames_add = classnames_add or []
        return {
            'url': url,
            'label': _('View live'),
            'classname': self.finalise_classname(
                classnames_add=classnames_add,
                classnames_exclude=classnames_exclude,
            ),
            'title': _('View %s live') % self.verbose_name,
            'icon': 'view',
            'target': '_blank',
        }

    def get_buttons_for_obj(self, obj, exclude=None, classnames_add=None, classnames_exclude=None):
        from actions.models import Action, Category
        from indicators.models import Indicator

        buttons = super().get_buttons_for_obj(obj, exclude, classnames_add, classnames_exclude)
        view_live_button = self.view_live_button(
            obj,
            classnames_add=classnames_add,
            classnames_exclude=classnames_exclude,
        )
        if view_live_button:
            buttons.append(view_live_button)
        if isinstance(obj, (Action, Category, Indicator)):
            dataset_buttons = get_dataset_buttons(self, obj, classnames_add or [], classnames_exclude)
            buttons.extend(dataset_buttons)
        return buttons


class AplansTabbedInterface[M: Model, F: ModelForm[Any] = ModelForm[Any]](TabbedInterface[M, F]):
    class BoundPanel(TabbedInterface.BoundPanel[Any, Any, Any]):
        pass

    def get_bound_panel(
        self,
        instance: M | None = None,
        request: HttpRequest | None = None,
        form=None,
        prefix='panel',
    ):
        if request is not None:
            req = admin_req(request)
            plan = req.get_active_admin_plan()
            user = req.user
            is_admin = user.is_general_admin_for_plan(plan)
        else:
            is_admin = False
        if not is_admin:
            for child in list(self.children):
                if isinstance(child, AdminOnlyPanel):
                    cast('list[Panel[Any]]', self.children).remove(child)

        return super().get_bound_panel(instance, request, form, prefix)


if TYPE_CHECKING:
    class PersistFiltersBase[M: Model](ModelFormView[M]):
        continue_editing_active: Callable[[], bool]
        model_name: str
    class InstanceSpecificViewBase[M: Model](InstanceSpecificView[M]):
        pass
else:
    class PersistFiltersBase[M: Model]: ...
    class InstanceSpecificViewBase[M: Model]: ...

# TODO: Reimplemented in admin_site/mixins.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class PersistFiltersEditingModelAdminMixin[M: Model](PersistFiltersBase[M]):
    def get_success_url(self):
        if hasattr(super(), 'continue_editing_active') and super().continue_editing_active():  # type: ignore[misc]
            return super().get_success_url()  # type: ignore[misc]
        model = self.model_name
        url = super().get_success_url()  # type: ignore[misc]
        if model is None:
            return url
        filter_qs = self.request.session.get(f'{model}_filter_querystring')
        if filter_qs is None:
            return url
        # Notice that urljoin will just overwrite any existing query
        # strings in the url.  The query strings would have to be
        # parsed, merged, and serialized if url contains query strings
        assert url is not None
        return urljoin(url, filter_qs)


# TODO: Reimplemented in admin_site/mixins.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class ContinueEditingModelAdminMixin[M: Model](PersistFiltersBase[M], InstanceSpecificViewBase[M]):
    instance: M
    url_helper: AdminURLHelper

    def continue_editing_active(self):
        return '_continue' in self.request.POST

    def get_success_url(self):
        if self.continue_editing_active():
            # Save and continue editing
            if not hasattr(self, 'pk_quoted'):
                pk = self.instance.pk
            else:
                pk = self.pk_quoted
            return self.url_helper.get_action_url('edit', pk)
        return super().get_success_url()

    def get_success_message_buttons(self, instance):
        if self.continue_editing_active():
            # Store a reference to instance here for get_success_url() above to
            # work in CreateView
            if not hasattr(self, 'pk_quoted') and not hasattr(self, 'instance'):
                self.instance = instance
            # Save and continue editing -> No edit button required
            return []

        button_url = self.url_helper.get_action_url('edit', quote(instance.pk))
        return [
            messages.button(button_url, _('Edit')),
        ]


# TODO: Reimplemented in admin_site/mixins.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class PlanRelatedViewModelAdminMixin[M: Model](PersistFiltersBase[M]):
    request: HttpRequest

    def form_valid(self, form, *args, **kwargs):
        obj = form.instance
        if isinstance(obj, PlanRelatedModel):
            # Sanity check to ensure we're saving the model to a currently active
            # action plan.
            active_plan = admin_req(self.request).user.get_active_admin_plan()
            plans = obj.get_plans()
            if len(plans):
                assert active_plan in plans

        return super().form_valid(form, *args, **kwargs)

    def dispatch(self, request: HttpRequest, *args, **kwargs):
        user = user_or_bust(request.user)
        instance = getattr(self, 'instance', None)
        # Check if we need to change the active action plan to be able to modify
        # the instance. This might happen e.g. when the user clicks on an edit link
        # in the email notification.
        if instance is not None and isinstance(instance, PlanRelatedModel):
            plan = user.get_active_admin_plan()
            instance_plans = instance.get_plans()
            if len(instance_plans) > 0 and plan not in instance_plans:
                querystring = QueryDict(mutable=True)
                querystring[REDIRECT_FIELD_NAME] = request.get_full_path()
                url = reverse('change-admin-plan', kwargs=dict(plan_id=instance_plans[0].id))
                return HttpResponseRedirect(url + '?' + querystring.urlencode())

        return super().dispatch(request, *args, **kwargs)


# TODO: Reimplemented in admin_site/mixins.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class ActivatePermissionHelperPlanContextModelAdminMixin[M: Model](ViewMixinBase[M]):
    permission_helper: PermissionHelper[M]

    @method_decorator(login_required)
    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Set the plan context for permission helper before dispatching request."""

        user = user_or_bust(request.user)
        if isinstance(self.permission_helper, PlanContextModelAdminPermissionHelper):
            with self.permission_helper.activate_plan_context(user.get_active_admin_plan()):
                ret = super().dispatch(request, *args, **kwargs)  # type: ignore[misc]
                # We trigger render here, because the plan context is needed
                # still in the render stage.
                if hasattr(ret, 'render'):
                    ret = ret.render()
            return ret
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]


# TODO: Reimplemented in admin_site/mixins.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class SetInstanceModelAdminMixin[M: Model](ViewMixinBase[M]):
    instance: M

    def setup(self, *args, **kwargs):
        with ctx_instance.activate(self.instance):
            super().setup(*args, **kwargs)  # type: ignore

    def dispatch(self, *args, **kwargs):
        with ctx_instance.activate(self.instance):
            return super().dispatch(*args, **kwargs)  # type: ignore


def execute_admin_post_save_tasks(instance: Model, user: User):
    handle_admin_save = getattr(instance, 'handle_admin_save', None)
    if handle_admin_save:
        handle_admin_save(
            context={
                'user': user,
                'operation': 'edit',
            },
        )
    success_message = _("%(model_name)s '%(object)s' updated.") % {
        'model_name': capfirst(instance._meta.verbose_name),
        'object': instance,
    }
    if not reversion.is_registered(instance):
        return
    with create_revision():
        set_comment(success_message)
        add_to_revision(instance)
        set_user(user)


# TODO: Partly reimplemented in admin_site/viewsets.py. Use that when
# implementing new classes or migrating away from ModelAdmin. Remove this class
# when ModelAdmin migration is finished.
class AplansEditView[M: Model](
    PersistFiltersEditingModelAdminMixin[M],
    ContinueEditingModelAdminMixin[M],
    PlanRelatedViewModelAdminMixin[M],
    ActivatePermissionHelperPlanContextModelAdminMixin[M],
    SetInstanceModelAdminMixin[M],
    EditView[M],
):
    def form_valid(self, form, *args, **kwargs):
        try:
            form_valid_return = super().form_valid(form, *args, **kwargs)
        except ProtectedError as e:
            for o in e.protected_objects:
                name = type(o)._meta.verbose_name_plural
                error = _('Error deleting items. Try first deleting any %(name)s that are in use.') % {'name': name}
                form.add_error(None, error)
                form.add_error(None, _('In use: "%(instance)s".') % {'instance': str(o)})
            messages.validation_error(self.request, self.get_error_message(), form)
            return self.render_to_response(self.get_context_data(form=form))

        execute_admin_post_save_tasks(form.instance, admin_req(self.request).user)
        return form_valid_return

    def get_error_message(self):
        if hasattr(self.instance, 'verbose_name_partitive'):
            model_name = self.instance.verbose_name_partitive  # pyright: ignore[reportAttributeAccessIssue]
        else:
            model_name = self.verbose_name

        return _('%s could not be created due to errors.') % capfirst(model_name)


# TODO: Reimplemented in admin_site/mixins.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class SuccessUrlEditPageModelAdminMixin[M: Model](InstanceSpecificViewBase[M]):
    """After editing a model instance, redirect to the edit page again instead of the index page."""

    def get_success_url(self):
        return self.url_helper.get_action_url('edit', self.instance.pk)


class AplansCreateView[M: Model](
    PersistFiltersEditingModelAdminMixin[M],
    ContinueEditingModelAdminMixin[M],
    PlanRelatedViewModelAdminMixin[M],
    SetInstanceModelAdminMixin[M],
    CreateView[M],
):
    request: HttpRequest

    def initialize_instance(self, request):
        if isinstance(self.instance, PlanRelatedModel):
            plan = request.user.get_active_admin_plan()
            self.instance.initialize_plan_defaults(plan)

    def setup(self, request, *args, **kwargs):
        self.instance = self.model()
        self.initialize_instance(request)
        super().setup(request, *args, **kwargs)

    def form_valid(self, form, *args, **kwargs):
        ret = super().form_valid(form, *args, **kwargs)

        if hasattr(form.instance, 'handle_admin_save'):
            form.instance.handle_admin_save(
                context={
                    'user': self.request.user,
                    'operation': 'create',
                },
            )

        return ret


class AplansIndexView[M: Model](ActivatePermissionHelperPlanContextModelAdminMixin[M], IndexView[M]):
    pass


# TODO: Partly reimplemented in admin_site/viewsets.py as SnippetViewSet. Use
# that when implementing new classes or migrating away from ModelAdmin. Remove
# this class when ModelAdmin migration is finished.
class AplansModelAdmin[M: Model](ModelAdmin[M]):
    model: type[M]
    edit_view_class = AplansEditView
    create_view_class = AplansCreateView
    index_view_class = AplansIndexView
    button_helper_class: type[ButtonHelper] = AplansButtonHelper
    permission_helper_class: type[PermissionHelper[M]]

    def __init__(self, *args, **kwargs):
        if not self.permission_helper_class and issubclass(self.model, PlanRelatedModel):
            self.permission_helper_class = PlanRelatedModelAdminPermissionHelper
        super().__init__(*args, **kwargs)

    def get_index_view_extra_js(self):
        ret = super().get_index_view_extra_js()
        return ret + ['admin_site/js/wagtail_customizations.js']


class CondensedInlinePanel[M: Model, RelatedM: Model](InlinePanel[M, RelatedM]):
    pass


if TYPE_CHECKING:
    class ModelFormViewMixin[M: Model](ModelFormView[M]):
        pass
else:
    class ModelFormViewMixin[M: Model]: ...


class InitializeFormWithPlanMixin[M: Model](ModelFormViewMixin[M]):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        user = user_or_bust(self.request.user)
        kwargs.update({'plan': user.get_active_admin_plan()})
        return kwargs


class InitializeFormWithInitialPlanMixin[M: Model](ModelFormViewMixin[M]):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()  # type: ignore
        kwargs.update({'initial_plan_id': self.request.session.get('initial_plan_id')})  # type: ignore
        return kwargs

    def dispatch(self, request, *args, **kwargs):
        # Retrieve the active plan and set the plan ID in the session
        if request.method == 'GET':
            active_plan = request.get_active_admin_plan()
            request.session['initial_plan_id'] = str(active_plan.id)

        # Proceed with the normal dispatch process
        return super().dispatch(request, *args, **kwargs)  # type: ignore


class InitializeFormWithUserMixin[M: Model](ModelFormViewMixin[M]):
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs


class ActivePlanEditView(SuccessUrlEditPageModelAdminMixin[Plan], AplansEditView[Plan]):
    @transaction.atomic()
    def form_valid(self, form):
        old_common_category_types = self.instance.common_category_types.all()
        new_common_category_types = form.cleaned_data['common_category_types']
        for added_cct in new_common_category_types.difference(old_common_category_types):
            # Create category type corresponding to this common category type and link it to this plan
            ct = added_cct.instantiate_for_plan(self.instance)
            # Create categories for the common categories having that common category type
            for common_category in added_cct.categories.all():
                common_category.instantiate_for_category_type(ct)
        for removed_cct in old_common_category_types.difference(new_common_category_types):
            try:
                self.instance.category_types.filter(common=removed_cct).delete()
            except ProtectedError:
                # Actually validation should have been done before this method is called, but it seems to work for now
                error = _(
                    'Could not remove common category type "%(removed_cct)" from the plan because categories '
                    'with the corresponding category type exist.',
                ) % {'removed_cct': removed_cct}
                form.add_error('common_category_types', error)
                messages.validation_error(self.request, self.get_error_message(), form)
                return self.render_to_response(self.get_context_data(form=form))
        return super().form_valid(form)
