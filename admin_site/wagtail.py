from condensedinlinepanel.edit_handlers import BaseCondensedInlinePanelFormSet
from condensedinlinepanel.edit_handlers import CondensedInlinePanel as WagtailCondensedInlinePanel
from django.conf import settings
from django.contrib.admin.utils import quote
from django.utils.text import capfirst
from django.utils.translation import gettext as _
from modeltrans.translator import get_i18n_field
from reversion.revisions import add_to_revision, create_revision, set_comment, set_user
from wagtail.admin import messages
from wagtail.admin.edit_handlers import FieldPanel, ObjectList, TabbedInterface
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.contrib.modeladmin.helpers import ButtonHelper, PermissionHelper
from wagtail.contrib.modeladmin.options import ModelAdmin
from wagtail.contrib.modeladmin.views import CreateView, EditView
from wagtailautocomplete.edit_handlers import AutocompletePanel as WagtailAutocompletePanel
from wagtailautocomplete.widgets import Autocomplete as WagtailAutocomplete


class AdminOnlyPanel(ObjectList):
    pass


class AplansAdminModelForm(WagtailAdminModelForm):
    pass


class AplansButtonHelper(ButtonHelper):
    edit_button_classnames = ['button-primary', 'icon', 'icon-edit']

    def view_live_button(self, obj, classnames_add=None, classnames_exclude=None):
        if obj is None or not hasattr(obj, 'get_view_url'):
            return None
        url = obj.get_view_url()
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


class ContinueEditingMixin:
    def get_success_url(self):
        if '_continue' in self.request.POST:
            # Save and continue editing
            if not hasattr(self, 'pk_quoted'):
                pk = self.instance.pk
            else:
                pk = self.pk_quoted
            return self.url_helper.get_action_url('edit', pk)
        else:
            return super().get_success_url()

    def get_success_message_buttons(self, instance):
        if '_continue' in self.request.POST:
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


class AplansEditView(ContinueEditingMixin, FormClassMixin, EditView):
    def form_valid(self, form, *args, **kwargs):
        form_valid_return = super().form_valid(form, *args, **kwargs)

        if hasattr(form.instance, 'handle_admin_save'):
            form.instance.handle_admin_save()

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


class AplansCreateView(ContinueEditingMixin, FormClassMixin, CreateView):
    def form_valid(self, form, *args, **kwargs):
        ret = super().form_valid(form, *args, **kwargs)

        if hasattr(form.instance, 'handle_admin_save'):
            form.instance.handle_admin_save()

        return ret


class AplansModelAdmin(ModelAdmin):
    edit_view_class = AplansEditView
    create_view_class = AplansCreateView
    button_helper_class = AplansButtonHelper

    def get_translation_tabs(self, instance, request):
        i18n_field = get_i18n_field(type(instance))
        if not i18n_field:
            return []
        tabs = []

        user = request.user
        plan = user.get_active_admin_plan()

        languages_by_code = {x[0]: x[1] for x in settings.LANGUAGES}

        for lang_code in plan.other_languages:
            fields = []
            for field in i18n_field.get_translated_fields():
                if field.language != lang_code:
                    continue
                fields.append(FieldPanel(field.name))
            tabs.append(ObjectList(fields, heading=languages_by_code[lang_code]))
        return tabs

    def insert_model_translation_tabs(self, model, panels, request, plan=None):
        i18n_field = get_i18n_field(model)
        if not i18n_field:
            return

        out = []
        if plan is None:
            plan = request.user.get_active_admin_plan()

        # languages_by_code = {x[0]: x[1] for x in settings.LANGUAGES}

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

    def _get_category_fields(self, plan, obj, with_initial=False):
        fields = {}
        if self.model == Action:
            filter_name = 'editable_for_actions'
        elif self.model == Indicator:
            filter_name = 'editable_for_indicators'
        else:
            raise Exception()

        for cat_type in plan.category_types.filter(**{filter_name: True}):
            qs = cat_type.categories.all()
            if obj and with_initial:
                initial = obj.categories.filter(type=cat_type)
            else:
                initial = None
            field = forms.ModelMultipleChoiceField(
                qs, label=cat_type.name, initial=initial, required=False,
            )
            field.category_type = cat_type
            fields['categories_%s' % cat_type.identifier] = field
        return fields


class EmptyFromTolerantBaseCondensedInlinePanelFormSet(BaseCondensedInlinePanelFormSet):
    """Remove empty new forms from data"""

    def process_post_data(self, data, *args, **kwargs):
        prefix = kwargs['prefix']

        initial_forms = int(data.get('%s-INITIAL_FORMS' % prefix, 0))
        total_forms = int(data.get('%s-TOTAL_FORMS' % prefix, 0))
        order = data.get('%s-ORDER' % prefix, None)
        if order is not None and order != '':
            order = order.lstrip('[').rstrip(']')
            if order == '':
                order = []
            else:
                order = [int(x) for x in order.split(',')]

        if total_forms:
            to_delete = []
            for idx in range(initial_forms, total_forms):
                keys = filter(lambda x: x.startswith('%s-%d-' % (prefix, idx)), data.keys())
                for key in keys:
                    if data[key]:
                        break
                else:
                    to_delete.append(idx)

            if to_delete:
                data = data.copy()

                data['%s-TOTAL_FORMS' % prefix] = str(total_forms - len(to_delete))
                if order is not None and order != '':
                    data['%s-ORDER' % prefix] = '[%s]' % (','.join([str(x) for x in order]))

            for idx in to_delete:
                keys = list(filter(lambda x: x.startswith('%s-%d-' % (prefix, idx)), data.keys()))
                for key in keys:
                    del data[key]
                if order:
                    order.remove(idx)

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


class PlanRelatedPermissionHelper(PermissionHelper):
    def get_plans(self, obj):
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
                ret += "\nsetTimeout(function() { $('#%s').attr('placeholder', '%s'); }, 5000);" % (id, quote(self.placeholder_text))
            return ret

        self.widget.get_context = get_context
        self.widget.render_js_init = render_js_init
