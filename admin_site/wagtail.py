from typing import List
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.admin.utils import quote
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.db import transaction
from django.db.models import ProtectedError
from django.forms.widgets import Select
from django.http.request import QueryDict
from django.http.response import HttpResponseRedirect
from django.urls.base import reverse
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from modeltrans.translator import get_i18n_field
from wagtail.admin import messages
from wagtail.admin.edit_handlers import FieldPanel, ObjectList, TabbedInterface
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.contrib.modeladmin.helpers import ButtonHelper, PermissionHelper
from wagtail.contrib.modeladmin.options import ModelAdmin, ModelAdminMenuItem
from wagtail.contrib.modeladmin.views import CreateView, EditView

from condensedinlinepanel.edit_handlers import BaseCondensedInlinePanelFormSet
from condensedinlinepanel.edit_handlers import \
    CondensedInlinePanel as WagtailCondensedInlinePanel
from reversion.revisions import (
    add_to_revision, create_revision, set_comment, set_user
)
from wagtailautocomplete.edit_handlers import \
    AutocompletePanel as WagtailAutocompletePanel

from aplans.types import WatchAdminRequest
from aplans.utils import PlanRelatedModel, PlanDefaultsModel
from actions.models import Plan


def insert_model_translation_panels(model, panels, request, plan=None) -> List:
    """Return a list of panels containing all of `panels` and language-specific panels for fields with i18n."""
    i18n_field = get_i18n_field(model)
    if not i18n_field:
        return panels

    out = []
    if plan is None:
        plan = request.user.get_active_admin_plan()

    field_map = {}
    for f in i18n_field.get_translated_fields():
        field_map.setdefault(f.original_name, {})[f.language] = f

    for p in panels:
        out.append(p)
        if not isinstance(p, FieldPanel):
            continue
        t_fields = field_map.get(p.field_name)
        if not t_fields:
            continue

        for lang_code in plan.other_languages:
            tf = t_fields.get(lang_code)
            if not tf:
                continue
            out.append(type(p)(tf.name))
    return out


def get_translation_tabs(instance, request, include_all_languages: bool = False, default_language=None):
    if default_language is None:
        default_language = settings.LANGUAGE_CODE

    i18n_field = get_i18n_field(type(instance))
    if not i18n_field:
        return []
    tabs = []

    user = request.user
    plan = user.get_active_admin_plan()

    languages_by_code = {x[0].lower(): x[1] for x in settings.LANGUAGES}
    if include_all_languages:
        # Omit main language because it's stored in the model field without a modeltrans language suffix
        languages = [lang for lang in languages_by_code.keys() if lang != default_language]
    else:
        languages = plan.other_languages
    for lang_code in languages:
        fields = []
        for field in i18n_field.get_translated_fields():
            if field.language != lang_code:
                continue
            fields.append(FieldPanel(field.name))
        tabs.append(ObjectList(fields, heading=languages_by_code[lang_code.lower()]))
    return tabs


class PlanRelatedPermissionHelper(PermissionHelper):
    def get_plans(self, obj):
        if isinstance(obj, PlanRelatedModel):
            return obj.get_plans()
        else:
            raise NotImplementedError('implement in subclass')

    def _obj_matches_active_plan(self, user, obj):
        obj_plans = self.get_plans(obj)
        active_plan = user.get_active_admin_plan()
        for obj_plan in obj_plans:
            if obj_plan == active_plan:
                return True
        return False

    def user_can_inspect_obj(self, user, obj):
        if not super().user_can_inspect_obj(user, obj):
            return False
        return self._obj_matches_active_plan(user, obj)

    def user_can_edit_obj(self, user, obj):
        if not super().user_can_edit_obj(user, obj):
            return False
        return self._obj_matches_active_plan(user, obj)

    def user_can_delete_obj(self, user, obj):
        if not super().user_can_edit_obj(user, obj):
            return False
        return self._obj_matches_active_plan(user, obj)


class AdminOnlyPanel(ObjectList):
    pass


class AplansAdminModelForm(WagtailAdminModelForm):
    pass


class PlanFilteredFieldPanel(FieldPanel):
    """Filters the related model queryset based on the active plan."""

    def on_form_bound(self):
        super().on_form_bound()

        field = self.bound_field.field
        user = self.request.user
        plan = user.get_active_admin_plan()

        related_model = field.queryset.model
        assert issubclass(related_model, PlanRelatedModel)
        field.queryset = related_model.filter_by_plan(plan, field.queryset)


class AplansButtonHelper(ButtonHelper):
    edit_button_classnames = ['button-primary', 'icon', 'icon-edit']

    def view_live_button(self, obj, classnames_add=None, classnames_exclude=None):
        if obj is None or not hasattr(obj, 'get_view_url'):
            return None
        if isinstance(obj, Plan):
            url = obj.get_view_url()
        else:
            url = obj.get_view_url(plan=self.request.user.get_active_admin_plan())
        if not url:
            return None

        classnames_add = classnames_add or []
        return {
            'url': url,
            'label': _('View live'),
            'classname': self.finalise_classname(
                classnames_add=classnames_add + ['icon', 'icon-view'],
                classnames_exclude=classnames_exclude
            ),
            'title': _('View %s live') % self.verbose_name,
            'target': '_blank',
        }

    def get_buttons_for_obj(self, obj, exclude=None, classnames_add=None,
                            classnames_exclude=None):
        buttons = super().get_buttons_for_obj(obj, exclude, classnames_add, classnames_exclude)
        view_live_button = self.view_live_button(
            obj, classnames_add=classnames_add, classnames_exclude=classnames_exclude
        )
        if view_live_button:
            buttons.append(view_live_button)
        return buttons


class AplansTabbedInterface(TabbedInterface):
    def get_form_class(self, request=None):
        return super().get_form_class()

    def on_request_bound(self):
        user = self.request.user
        plan = user.get_active_admin_plan()

        if not user.is_general_admin_for_plan(plan):
            for child in list(self.children):
                if isinstance(child, AdminOnlyPanel):
                    self.children.remove(child)

        super().on_request_bound()


class FormClassMixin:
    def get_form_class(self):
        handler = self.get_edit_handler()
        if isinstance(handler, AplansTabbedInterface):
            return handler.get_form_class(self.request)
        else:
            return handler.get_form_class()


class PersistIndexViewFiltersMixin:
    def dispatch(self, request, *args, **kwargs):
        result = super().dispatch(request, *args, **kwargs)
        model = getattr(self, 'model_name')
        if model is None:
            return result
        request.session[f'{model}_filter_querystring'] = super().get_query_string()
        return result


class PersistFiltersEditingMixin:
    def get_success_url(self):
        if hasattr(super(), 'continue_editing_active') and super().continue_editing_active():
            return super().get_success_url()
        model = getattr(self, 'model_name')
        url = super().get_success_url()
        if model is None:
            return url
        filter_qs = self.request.session.get(f'{model}_filter_querystring')
        if filter_qs is None:
            return url
        # Notice that urljoin will just overwrite any existing query
        # strings in the url.  The query strings would have to be
        # parsed, merged, and serialized if url contains query strings
        return urljoin(url, filter_qs)


class ContinueEditingMixin():
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
        else:
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
            messages.button(button_url, _('Edit'))
        ]


class PlanRelatedViewMixin:
    def form_valid(self, form, *args, **kwargs):
        obj = form.instance
        if isinstance(obj, PlanRelatedModel):
            # Sanity check to ensure we're saving the model to a currently active
            # action plan.
            active_plan = self.request.user.get_active_admin_plan()
            plans = obj.get_plans()
            assert active_plan in plans

        return super().form_valid(form, *args, **kwargs)

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        instance = getattr(self, 'instance', None)
        # Check if we need to change the active action plan to be able to modify
        # the instance. This might happen e.g. when the user clicks on an edit link
        # in the email notification.
        if (instance is not None and isinstance(instance, PlanRelatedModel) and
                user is not None and user.is_authenticated):
            plan = user.get_active_admin_plan()
            instance_plans = instance.get_plans()
            if plan not in instance_plans:
                querystring = QueryDict(mutable=True)
                querystring[REDIRECT_FIELD_NAME] = request.get_full_path()
                url = reverse('change-admin-plan', kwargs=dict(plan_id=instance_plans[0].id))
                return HttpResponseRedirect(url + '?' + querystring.urlencode())

        return super().dispatch(request, *args, **kwargs)


class AplansEditView(PersistFiltersEditingMixin, ContinueEditingMixin, FormClassMixin,
                     PlanRelatedViewMixin, EditView):
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

        if hasattr(form.instance, 'handle_admin_save'):
            form.instance.handle_admin_save(context={
                'user': self.request.user,
                'operation': 'edit'
            })

        with create_revision():
            set_comment(self.get_success_message(self.instance))
            add_to_revision(self.instance)
            set_user(self.request.user)

        return form_valid_return

    def get_error_message(self):
        if hasattr(self.instance, 'verbose_name_partitive'):
            model_name = self.instance.verbose_name_partitive
        else:
            model_name = self.verbose_name

        return _("%s could not be created due to errors.") % capfirst(model_name)


class SuccessUrlEditPageMixin:
    """After editing a model instance, redirect to the edit page again instead of the index page."""
    def get_success_url(self):
        return self.url_helper.get_action_url('edit', self.instance.pk)


class ActivePlanEditView(SuccessUrlEditPageMixin, AplansEditView):
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
                error = _(f"Could not remove common category type '{removed_cct}' from the plan because categories "
                          "with the corresponding category type exist.")
                form.add_error('common_category_types', error)
                messages.validation_error(self.request, self.get_error_message(), form)
                return self.render_to_response(self.get_context_data(form=form))
        return super().form_valid(form)


class AplansCreateView(PersistFiltersEditingMixin, ContinueEditingMixin, FormClassMixin,
                       PlanRelatedViewMixin, CreateView):
    request: WatchAdminRequest

    def get_instance(self):
        instance = super().get_instance()
        # If it is a model directly or indirectly related to the
        # active plan, ensure the 'plan' field or other plan related
        # fields get set correctly.
        if isinstance(instance, PlanDefaultsModel):
            plan = self.request.user.get_active_admin_plan()
            instance.initialize_plan_defaults(plan)
        return instance

    def form_valid(self, form, *args, **kwargs):
        ret = super().form_valid(form, *args, **kwargs)

        if hasattr(form.instance, 'handle_admin_save'):
            form.instance.handle_admin_save(context={
                'user': self.request.user,
                'operation': 'create'
            })

        return ret


class SafeLabelModelAdminMenuItem(ModelAdminMenuItem):
    def get_label_from_context(self, context, request):
        # This method may be trivial, but we override it elsewhere
        return context.get('label')

    def get_context(self, request):
        ret = super().get_context(request)
        label = self.get_label_from_context(ret, request)
        if label:
            ret['label'] = mark_safe(label)
        return ret


class AplansModelAdmin(ModelAdmin):
    edit_view_class = AplansEditView
    create_view_class = AplansCreateView
    button_helper_class = AplansButtonHelper

    def __init__(self, *args, **kwargs):
        if not self.permission_helper_class and issubclass(self.model, PlanRelatedModel):
            self.permission_helper_class = PlanRelatedPermissionHelper
        super().__init__(*args, **kwargs)

    def get_index_view_extra_js(self):
        ret = super().get_index_view_extra_js()
        return ret + ['admin_site/js/wagtail_customizations.js']

    def get_menu_item(self, order=None):
        return SafeLabelModelAdminMenuItem(self, order or self.get_menu_order())


class EmptyFromTolerantBaseCondensedInlinePanelFormSet(BaseCondensedInlinePanelFormSet):
    """Remove empty new forms from data"""

    def process_post_data(self, data, *args, **kwargs):
        prefix = kwargs['prefix']

        initial_forms = int(data.get('%s-INITIAL_FORMS' % prefix, 0))
        total_forms = int(data.get('%s-TOTAL_FORMS' % prefix, 0))

        delete = data.get('%s-DELETE' % prefix, '').lstrip('[').rstrip(']')
        if delete:
            delete = [int(x) for x in delete.split(',')]
        else:
            delete = []

        for idx in range(initial_forms, total_forms):
            keys = filter(lambda x: x.startswith('%s-%d-' % (prefix, idx)), data.keys())
            for key in keys:
                if data[key]:
                    break
            else:
                delete.append(idx)

        if delete:
            data = data.copy()
            data['%s-DELETE' % prefix] = '[%s]' % (','.join([str(x) for x in sorted(delete)]))

        return super().process_post_data(data, *args, **kwargs)


class CondensedInlinePanel(WagtailCondensedInlinePanel):
    formset_class = EmptyFromTolerantBaseCondensedInlinePanelFormSet

    def on_instance_bound(self):
        label = self.label
        new_card_header_text = self.new_card_header_text
        super().on_instance_bound()
        related_name = {
            'related_verbose_name': self.db_field.related_model._meta.verbose_name,
        }
        self.label = label or _('Add %(related_verbose_name)s') % related_name
        self.new_card_header_text = new_card_header_text or _('New %(related_verbose_name)s') % related_name


class AutocompletePanel(WagtailAutocompletePanel):
    def __init__(self, field_name, target_model=None, placeholder_text=None, **kwargs):
        self.placeholder_text = placeholder_text
        super().__init__(field_name, target_model, **kwargs)

    def clone(self):
        return self.__class__(
            field_name=self.field_name,
            target_model=self.target_model_kwarg,
            placeholder_text=self.placeholder_text,
        )

    def on_model_bound(self):
        super().on_model_bound()
        self.widget.placeholder_text = self.placeholder_text

        old_get_context = self.widget.get_context

        def get_context(self, *args, **kwargs):
            context = old_get_context(self, *args, **kwargs)
            context['widget']['placeholder_text'] = self.placeholder_text
            return context

        old_render_js_init = self.widget.render_js_init

        def render_js_init(self, id):
            ret = old_render_js_init(self, id)
            if self.placeholder_text:
                ret += "\nsetTimeout(function() { $('#%s').attr('placeholder', '%s'); }, 5000);" % (
                    id, quote(self.placeholder_text)
                )
            return ret

        self.widget.get_context = get_context
        self.widget.render_js_init = render_js_init


class CondensedPanelSingleSelect(Select):
    def format_value(self, value):
        if value is None:
            return ''
        return str(value)


class InitializeFormWithPlanMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'plan': self.request.user.get_active_admin_plan()})
        return kwargs


class InitializeFormWithUserMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({'user': self.request.user})
        return kwargs
