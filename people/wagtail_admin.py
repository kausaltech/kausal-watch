import logging
import typing

from dal import autocomplete
from datetime import timedelta
from django.contrib.admin.utils import display_for_value
from django.contrib.admin.widgets import AdminFileWidget
from django.db import transaction
from django.db.models import F
from django.forms import BooleanField, ModelMultipleChoiceField
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import get_language, gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, ObjectList, TabbedInterface
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.contrib.modeladmin.views import IndexView

from admin_site.wagtail import (
    AplansModelAdmin, AplansAdminModelForm, AplansCreateView, AplansEditView, InitializeFormWithPlanMixin,
    InitializeFormWithUserMixin, get_translation_tabs
)
from aplans.types import WatchAdminRequest
from aplans.utils import naturaltime

from .admin import IsContactPersonFilter
from .models import Person
from orgs.models import OrganizationPlanAdmin

if typing.TYPE_CHECKING:
    from users.models import User


logger = logging.getLogger(__name__)


def smart_truncate(content, length=100, suffix='...'):
    if len(content) <= length:
        return content
    else:
        return ' '.join(content[:length + 1].split(' ')[0:-1]) + suffix


class AvatarWidget(AdminFileWidget):
    template_name = 'admin/avatar_widget.html'


class PersonForm(AplansAdminModelForm):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.created_by = self.user

    def save(self, commit=True):
        if 'image' in self.files:
            self.instance.image_cropping = None
        return super().save(commit)


class PersonFormForGeneralAdmin(PersonForm):
    is_admin_for_active_plan = BooleanField(required=False, label=_('is plan admin'))
    organization_plan_admin_orgs = ModelMultipleChoiceField(
        queryset=None, required=False, widget=autocomplete.ModelSelect2Multiple(url='organization-autocomplete'),
        label=_('plan admin organizations'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert self.user.is_general_admin_for_plan(self.plan)
        self.fields['organization_plan_admin_orgs'].queryset = (
            self.plan.get_related_organizations().filter(dissolution_date=None)
        )
        if self.instance.pk is not None:
            self.fields['organization_plan_admin_orgs'].initial = (
                self.instance.organization_plan_admins.filter(plan=self.plan).values_list('organization', flat=True)
            )

    def save(self, commit=True):
        instance = super().save(commit)
        is_admin_for_active_plan = self.cleaned_data.get('is_admin_for_active_plan')
        if is_admin_for_active_plan is True:
            instance.general_admin_plans.add(self.plan)
        elif is_admin_for_active_plan is False:
            instance.general_admin_plans.remove(self.plan)

        organization_plan_admin_orgs = self.cleaned_data.get('organization_plan_admin_orgs')
        if organization_plan_admin_orgs is not None:
            with transaction.atomic():
                OrganizationPlanAdmin.objects.filter(plan=self.plan, person=instance).delete()
                for org in organization_plan_admin_orgs:
                    OrganizationPlanAdmin.objects.create(organization=org, plan=self.plan, person=instance)
        return instance


class PersonEditHandler(TabbedInterface):
    def on_form_bound(self):
        if self.request:
            plan = self.request.user.get_active_admin_plan()
            if self.form.initial.get('organization') is None:
                self.form.initial['organization'] = plan.organization
            if self.instance.pk is not None:
                self.form.initial['is_admin_for_active_plan'] = plan in self.instance.general_admin_plans.all()
        super().on_form_bound()


class PersonCreateView(InitializeFormWithPlanMixin, InitializeFormWithUserMixin, AplansCreateView):
    def form_valid(self, form, *args, **kwargs):
        # Make sure form only contains is_admin_for_active_plan
        # TODO: Also do this for organization_plan_admin_orgs?
        plan = self.request.user.get_active_admin_plan()
        is_general_admin = self.request.user.is_general_admin_for_plan(plan)
        contains_admin_flag = form.cleaned_data.get('is_admin_for_active_plan') is not None

        def iff(a, b):
            return (a and b) or (not a and not b)

        assert iff(contains_admin_flag, is_general_admin)
        return super().form_valid(form, *args, **kwargs)


class PersonEditView(InitializeFormWithPlanMixin, InitializeFormWithUserMixin, AplansEditView):
    pass


class PersonIndexView(IndexView):
    def get_ordering(self, request, queryset):
        ret = super().get_ordering(request, queryset)
        out = []
        for order in ret:
            field = order
            if order[0] == '-':
                field = field[1:]
                desc = True
            else:
                desc = False
            if field != 'user__last_login':
                out.append(order)
                continue
            order = F('user__last_login')
            if desc:
                order = order.desc(nulls_last=True)
            else:
                order = order.asc(nulls_first=True)
            out.append(order)
        return out


class PersonPermissionHelper(PermissionHelper):
    def _user_can_edit_or_delete(self, user, person):
        if user.is_superuser:
            return True
        # The creating user has edit rights until the created user first logs in
        if person.created_by == user and not person.user.last_login:
            return True

        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            related_orgs = plan.get_related_organizations().filter(dissolution_date=None)
            if person.organization in related_orgs:
                return True

        return False

    def user_can_edit_obj(self, user: 'User', obj: Person):
        if not super().user_can_edit_obj(user, obj):
            return False
        # Users can always edit themselves
        if obj.user == user:
            return True
        return self._user_can_edit_or_delete(user, obj)

    def user_can_delete_obj(self, user, obj: Person):
        if not super().user_can_delete_obj(user, obj):
            return False
        return self._user_can_edit_or_delete(user, obj)

    def user_can_create(self, user):
        if not super().user_can_create(user):
            return False
        return True


class PersonAdmin(AplansModelAdmin):
    model = Person
    create_view_class = PersonCreateView
    edit_view_class = PersonEditView
    index_view_class = PersonIndexView
    permission_helper_class = PersonPermissionHelper
    menu_icon = 'user'
    menu_label = _('People')
    menu_order = 10
    exclude_from_explorer = False
    search_fields = ('first_name', 'last_name', 'title')
    list_filter = (IsContactPersonFilter,)

    def get_queryset(self, request):
        plan = request.user.get_active_admin_plan()
        qs = super().get_queryset(request).available_for_plan(plan)
        return qs

    def get_empty_value_display(self, field=None):
        if getattr(field, '_name', field) == 'last_logged_in':
            return display_for_value(False, None, boolean=True)
        return super().get_empty_value_display(field)

    def get_list_display(self, request: WatchAdminRequest):
        plan = request.get_active_admin_plan()

        def edit_url(obj):
            if self.permission_helper.user_can_edit_obj(request.user, obj):
                return self.url_helper.get_action_url('edit', obj.pk)
            else:
                return None

        def avatar(obj):
            avatar_url = obj.get_avatar_url(request, size='50x50')
            if not avatar_url:
                return ''
            img = format_html('<span class="avatar"><img src="{}" /></span>', avatar_url)
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, img)
            else:
                return img
        avatar.short_description = ''

        def first_name(obj):
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, obj.first_name)
            else:
                return obj.first_name
        first_name.short_description = _('first name')
        first_name.admin_order_field = 'first_name'

        def last_name(obj):
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, obj.last_name)
            else:
                return obj.last_name
        last_name.short_description = _('last name')
        last_name.admin_order_field = 'last_name'

        fields = [avatar, first_name, last_name, 'title', 'organization']

        def last_logged_in(obj):
            user = obj.user
            if not user or not user.last_login:
                return None
            now = timezone.now()
            delta = now - user.last_login
            if delta > timedelta(days=30):
                return user.last_login.date()
            return naturaltime(delta)
        last_logged_in.short_description = _('last login')
        last_logged_in.admin_order_field = 'user__last_login'
        last_logged_in._name = 'last_logged_in'

        def is_plan_admin(obj: Person):
            user: User = obj.user
            if user is None:
                return False
            return user.is_general_admin_for_plan(plan)
        is_plan_admin.short_description = _('is plan admin')
        is_plan_admin._name = 'is_plan_admin'
        is_plan_admin.boolean = True

        user = request.user
        if user.is_general_admin_for_plan(plan):
            fields.append(is_plan_admin)
            fields.append(last_logged_in)
            fields.append('participated_in_training')

        def contact_for_actions(obj):
            return '; '.join([smart_truncate(str(act), 40) for act in obj.plan_contact_for_actions])
        contact_for_actions.short_description = _('contact for actions')

        def contact_for_indicators(obj):
            return '; '.join([smart_truncate(str(ind), 40) for ind in obj.plan_contact_for_indicators])
        contact_for_indicators.short_description = _('contact for indicators')

        contact_person_filter = request.GET.get('contact_person', '')
        if contact_person_filter == 'action':
            fields.append(contact_for_actions)
        elif contact_person_filter == 'indicator':
            fields.append(contact_for_indicators)

        return fields

    basic_panels = [
        FieldPanel('first_name'),
        FieldPanel('last_name'),
        FieldPanel('email'),
        FieldPanel('title'),
        FieldPanel(
            'organization',
            widget=autocomplete.ModelSelect2(url='organization-autocomplete'),
        ),
        FieldPanel('image', widget=AvatarWidget),
    ]

    def get_edit_handler(self, instance, request):
        basic_panels = list(self.basic_panels)
        user = request.user
        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            form_class = PersonFormForGeneralAdmin
            basic_panels.append(FieldPanel('participated_in_training'))
            basic_panels.append(FieldPanel('is_admin_for_active_plan'))
            basic_panels.append(FieldPanel(
                'organization_plan_admin_orgs',
                widget=autocomplete.ModelSelect2Multiple(url='organization-autocomplete'),
            ))
            # FIXME: This saves ActionContactPerson instances without specifying `order`, which leads to duplicates of the
            # default value.
            # TODO: No way to specify `primary_contact`.
            # Recall that we tried using inline panels (changing the other ForeignKey in the model to a ParentalKey and
            # adding some workarounds) for `actioncontactperson_set`, but came across the problem that it screws up the
            # ordering because the order as displayed in the person admin view is not what we want -- the order we want
            # should rather be the one as specified in the action edit view.
            basic_panels.append(FieldPanel(
                'contact_for_actions_unordered',
                widget=autocomplete.ModelSelect2Multiple(url='action-autocomplete'),
            ))
        else:
            form_class = PersonForm

        tabs = [ObjectList(basic_panels, heading=_('General'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return PersonEditHandler(tabs, base_form_class=form_class)


modeladmin_register(PersonAdmin)
