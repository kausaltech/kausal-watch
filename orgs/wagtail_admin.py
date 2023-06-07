# Parts adapted from https://posts-by.lb.ee/building-a-configurable-taxonomy-in-wagtail-django-94ca1080fb28
from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.urls import re_path
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.forms import ClusterForm
from wagtail import VERSION as WAGTAIL_VERSION
# from wagtail.admin.panels import FieldPanel, ObjectList, TabbedInterface
from wagtail.admin.edit_handlers import FieldPanel, ObjectList, TabbedInterface, get_form_for_model
from wagtail.contrib.modeladmin.helpers import AdminURLHelper, ButtonHelper, PermissionHelper
from wagtail.contrib.modeladmin.mixins import ThumbnailMixin
from wagtail.contrib.modeladmin.options import ModelAdmin
from wagtailgeowidget import __version__ as WAGTAILGEOWIDGET_VERSION

from .forms import NodeForm
from .models import Organization, OrganizationMetadataAdmin
from .views import (
    OrganizationCreateView, OrganizationEditView, SetOrganizationRelatedToActivePlanView, CreateChildNodeView,
)
from admin_site.wagtail import CondensedInlinePanel, get_translation_tabs
# from aplans.context_vars import ctx_instance, ctx_request
from aplans.extensions import modeladmin_register
from people.chooser import PersonChooser

if int(WAGTAILGEOWIDGET_VERSION.split('.')[0]) >= 7:
    from wagtailgeowidget.panels import GoogleMapsPanel
else:
    from wagtailgeowidget.edit_handlers import GoogleMapsPanel


class NodeButtonHelper(ButtonHelper):
    """Custom button functionality for node listing buttons."""

    def prepare_classnames(self, start=None, add=None, exclude=None):
        """Parse classname sets into final css classess list."""
        classnames = start or []
        classnames.extend(add or [])
        return self.finalise_classname(classnames, exclude or [])

    def add_child_button(self, pk, **kwargs):
        """Build a add child button, to easily add a child under node."""
        classnames = self.prepare_classnames(
            start=self.edit_button_classnames + ['icon', 'icon-plus'],
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude')
        )
        return {
            'classname': classnames,
            'label': _("Add child"),
            'title': _("Add child under this node"),
            'url': self.url_helper.get_action_url('add_child', quote(pk)),
        }

    def edit_subtree_button(self, pk, **kwargs):
        classnames = self.prepare_classnames(
            start=self.edit_button_classnames + ['icon', 'icon-edit'],
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude')
        )
        return {
            'classname': classnames,
            'label': _("Edit subtree"),
            'title': _("Edit subtree rooted at this %s") % self.verbose_name,
            'url': self.url_helper.get_action_url('edit_subtree', quote(pk)),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)

        add_child_button = self.add_child_button(
            pk=getattr(obj, self.opts.pk.attname),
            **kwargs
        )
        buttons.append(add_child_button)

        # TODO: Put this in when we have implemented the subtree editor
        # edit_subtree_button = self.edit_subtree_button(
        #     pk=getattr(obj, self.opts.pk.attname),
        #     **kwargs
        # )
        # buttons.append(edit_subtree_button)

        return buttons


class NodeAdmin(ModelAdmin):
    list_display = ('get_as_listing_header', 'get_parent')
    button_helper_class = NodeButtonHelper
    panels = [
        FieldPanel('name', heading=_("Name")),
    ]

    def add_child_view(self, request, instance_pk):
        """Generate a class-based view to provide 'add child' functionality."""
        # instance_pk will become the default selected parent_pk
        # TODO: Since CreateChildNodeView is a CreateView, it checks for user_can_create permissions. However, when
        # adding a child, we also should check that the user has permissions for the parent of the new instance.
        return CreateChildNodeView.as_view(model_admin=self, parent_pk=instance_pk)(request)

    def include_organization_in_active_plan_view(self, request, instance_pk):
        # FIXME: This is specific to Organization, but this class should be for generic nodes
        return SetOrganizationRelatedToActivePlanView.as_view(
            model_admin=self,
            org_pk=instance_pk,
            set_related=True,
        )(request)

    def exclude_organization_from_active_plan_view(self, request, instance_pk):
        # FIXME: This is specific to Organization, but this class should be for generic nodes
        return SetOrganizationRelatedToActivePlanView.as_view(
            model_admin=self,
            org_pk=instance_pk,
            set_related=False,
        )(request)

    def get_admin_urls_for_registration(self):
        """Add the new url for add child page to the registered URLs."""
        urls = super().get_admin_urls_for_registration()
        add_child_url = re_path(
            self.url_helper.get_action_url_pattern('add_child'),
            self.add_child_view,
            name=self.url_helper.get_action_url_name('add_child')
        )
        include_organization_in_active_plan_url = re_path(
            self.url_helper.get_action_url_pattern('include_organization_in_active_plan'),
            self.include_organization_in_active_plan_view,
            name=self.url_helper.get_action_url_name('include_organization_in_active_plan')
        )
        exclude_organization_from_active_plan_url = re_path(
            self.url_helper.get_action_url_pattern('exclude_organization_from_active_plan'),
            self.exclude_organization_from_active_plan_view,
            name=self.url_helper.get_action_url_name('exclude_organization_from_active_plan')
        )
        return urls + (
            add_child_url,
            include_organization_in_active_plan_url,
            exclude_organization_from_active_plan_url,
        )

class OrganizationPermissionHelper(PermissionHelper):
    def user_can_list(self, user):
        return True

    def user_can_create(self, user):
        # A user can create an organization if they can edit *any* organization. We just need to make sure that they can
        # only create organizations that are children of something they can edit.
        # TODO: Write tests to make sure we check in validation whether the user has permissions depending on the chosen
        # parent
        if user.is_superuser:
            return True
        # TODO: The following is the old logic, which we may reinstate when we thought about how to handle permissions
        # best.
        # person = user.get_corresponding_person()
        # return person and person.metadata_adminable_organizations.exists()
        # For now we allow general admins (for any plan) to create organizations.
        return user.is_general_admin_for_plan()

    def user_can_edit_obj(self, user, obj: Organization):
        return obj.user_can_edit(user)

    def user_can_delete_obj(self, user, obj: Organization):
        return obj.user_can_edit(user)


class OrganizationURLHelper(AdminURLHelper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @cached_property
    def index_url(self):
        # TODO: Remove this shim and delete org_admin_legacy once everything is upgraded to Wagtail 5
        if WAGTAIL_VERSION < (3, 0):
            # FIXME: This is a workaround to switch the only_added_to_plan filter on by default, but it causes
            # undesired behavior, e.g., resetting filters after editing an organization
            return f'{super().index_url}?only_added_to_plan=true'
        return super().index_url


class OrganizationForm(NodeForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_parent(self):
        parent = super().clean_parent()
        if self.instance._state.adding:
            return parent
        # If a user has edit access to an organization only because they can edit an ancestor, prevent them from losing
        # edit rights by moving it to a parent which they cannot edit (or make it a root). For now, only allow
        # superusers to set roots. (Only editable organizations are avaible as parent choices anyway.)
        if parent is None and not self.user.is_superuser:
            # On the other hand, allow direct metadata admins of a top level organizations to save the org when editing
            if (
                self.instance.parent is None and
                OrganizationMetadataAdmin.objects
                    .filter(person=self.user.person)
                    .filter(organization=self.instance)
                    .exists()
            ):
                return parent
            # For now, allow for general plan admins
            if self.instance.parent is None and self.user.is_general_admin_for_plan():
                return parent
            raise ValidationError(_("Creating organizations without a parent not allowed."), code='invalid_parent')
        return parent

    def save(self, *args, **kwargs):
        creating = self.instance._state.adding
        result = super().save(*args, **kwargs)
        if creating and self.instance.parent is None:
            # When creating a new root organization make sure the creator retains edit permissions
            self.instance.metadata_admins.add(self.user.person)
        return result


class OrganizationEditHandler(TabbedInterface):
    def get_form_class(self):
        # Adapted from BaseFormEditHandler.get_form_class to do something similar as if we had set base_form_class to
        # a form like this that we could put in forms.py:
        # class OrganizationForm(NodeForm):
        #     class Meta:
        #         model = Organization
        #         fields = ['parent', 'classification', 'name', 'abbreviation', 'founding_date', 'dissolution_date']
        # However, we can't just set base_form_class because we can't use OrganizationForm yet at the time of class
        # definition due to circular dependencies between this file and forms.py. (TODO: Have things changed after
        # refactoring to separate extensions package?)

        # We need the request in the model or form for OrganizationAdmin in order to set the plan of the
        # OrganizationAdmin instance to the currently active plan. However, we only have access to the request in the
        # view or edit handler. Django-modelcluster seems to offer no way to customize the formset / form classes it
        # creates by metaprogramming, so we hack the request into it like this:
        class PlanSpecificOrganizationAdminForm(ClusterForm):
            plan = self.request.user.get_active_admin_plan()

            def save(self, *args, **kwargs):
                self.instance.plan = self.plan
                return super().save(*args, **kwargs)

        formsets = self.required_formsets()
        formsets['organization_plan_admins']['form'] = PlanSpecificOrganizationAdminForm
        return get_form_for_model(
            self.model,
            form_class=OrganizationForm,
            fields=self.required_fields(),
            formsets=formsets,
            widgets=self.widget_overrides())


class OrganizationButtonHelper(NodeButtonHelper):
    def add_child_button(self, pk, **kwargs):
        result = super().add_child_button(pk, **kwargs)
        result['label'] = _("Add suborganization")
        result['title'] = _("Add suborganization under this organization")
        return result

    def include_organization_in_active_plan_button(self, pk, **kwargs):
        classnames = self.prepare_classnames(
            start=self.edit_button_classnames + ['icon', 'icon-fa-link'],
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude')
        )
        return {
            'classname': classnames,
            'label': _("Include in plan"),
            'title': _("Include this organization in the active plan"),
            'url': self.url_helper.get_action_url('include_organization_in_active_plan', quote(pk)),
        }

    def exclude_organization_from_active_plan_button(self, pk, **kwargs):
        classnames = self.prepare_classnames(
            start=self.edit_button_classnames + ['icon', 'icon-fa-unlink'],  # icon-fa-link-slash if we used FA 6
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude')
        )
        return {
            'classname': classnames,
            'label': _("Exclude from plan"),
            'title': _("Exclude this organization from the active plan"),
            'url': self.url_helper.get_action_url('exclude_organization_from_active_plan', quote(pk)),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)

        # Show "include in / exclude from active plan" button if user has permission and it's a root organization
        plan = self.request.user.get_active_admin_plan()
        if obj.user_can_change_related_to_plan(self.request.user, plan) and obj.is_root():
            # FIXME: Duplicates a check in IncludeOrganizationInActivePlanView
            if obj.pk in plan.related_organizations.values_list('pk', flat=True):
                exclude_organization_from_active_plan_button = self.exclude_organization_from_active_plan_button(
                    pk=getattr(obj, self.opts.pk.attname),
                    **kwargs
                )
                buttons.append(exclude_organization_from_active_plan_button)
            else:
                include_organization_in_active_plan_button = self.include_organization_in_active_plan_button(
                    pk=getattr(obj, self.opts.pk.attname),
                    **kwargs
                )
                buttons.append(include_organization_in_active_plan_button)

        return buttons


@modeladmin_register
class OrganizationAdmin(ThumbnailMixin, NodeAdmin):
    model = Organization
    menu_label = _("Organizations")
    menu_icon = 'fa-sitemap'
    menu_order = 9000
    button_helper_class = OrganizationButtonHelper
    permission_helper_class = OrganizationPermissionHelper
    url_helper_class = OrganizationURLHelper
    create_view_class = OrganizationCreateView
    edit_view_class = OrganizationEditView
    search_fields = ('name', 'abbreviation')
    list_display = ('admin_thumb',) + NodeAdmin.list_display + ('abbreviation',)
    list_display_add_buttons = NodeAdmin.list_display[0]
    thumb_image_field_name = 'logo'

    # TODO: Remove this shim and delete org_admin_legacy once everything is upgraded to Wagtail 5
    if WAGTAIL_VERSION < (3, 0):
        from .org_admin_legacy import LegacyOrganizationIndexView
        index_view_class = LegacyOrganizationIndexView

    basic_panels = NodeAdmin.panels + [
        FieldPanel(
            # virtual field, needs to be specified in the form
            'parent', heading=pgettext_lazy('organization', 'Parent')
        ),
        FieldPanel('logo'),
        FieldPanel('abbreviation'),
        FieldPanel('internal_abbreviation'),
        # Don't allow editing identifiers at this point
        # CondensedInlinePanel('identifiers', panels=[
        #     FieldPanel('namespace', widget=CondensedPanelSingleSelect),
        #     FieldPanel('identifier'),
        # ]),
        FieldPanel('description'),
        FieldPanel('url'),
        FieldPanel('email'),
    ]

    permissions_panels = [
        CondensedInlinePanel(
            'organization_plan_admins',
            panels=[
                # FieldPanel('plan'),  # active plan is automatically set
                FieldPanel('person', widget=PersonChooser),
            ],
            heading=_("Plan admins"),
            help_text=_("People who can edit plan-specific content related to this organization"),
        ),
        CondensedInlinePanel(
            'organization_metadata_admins',
            panels=[
                FieldPanel('person', widget=PersonChooser),
            ],
            heading=_("Metadata admins"),
            help_text=_("People who can edit data of this organization and suborganizations but no plan-specific "
                        "content"),
        ),
    ]

    def get_list_display(self, request):
        # Display "Is in plan" column only if we don't filter by that anyway
        if request.GET.get('only_added_to_plan'):
            return self.list_display

        plan = request.user.get_active_admin_plan()

        def is_in_plan(org):
            return org.id in (related.id for related in Organization.objects.available_for_plan(plan))
        is_in_plan.short_description = _("Is in plan")
        is_in_plan.boolean = True
        return self.list_display + (is_in_plan,)

    # def get_edit_handler(self):
    # TODO: When migrated to Wagtail >= 3, remove deprecated arguments
    def get_edit_handler(self, instance=None, request=None):
        if WAGTAIL_VERSION >= (3, 0):
            assert instance is None
            assert request is None
            request = ctx_request.get()
            instance = ctx_instance.get()

        basic_panels = list(self.basic_panels)
        if request.user.is_superuser:
            basic_panels.append(GoogleMapsPanel('location'))

        permissions_panels = list(self.permissions_panels)
        tabs = [
            ObjectList(basic_panels, heading=_('Basic information')),
            ObjectList(permissions_panels, heading=_('Permissions')),
        ]

        i18n_tabs = get_translation_tabs(instance, request, include_all_languages=True)
        tabs += i18n_tabs

        if WAGTAIL_VERSION >= (3, 0):
            plan = request.user.get_active_admin_plan()
            return OrganizationEditHandler(plan, tabs, base_form_class=OrganizationForm)
        else:
            return OrganizationEditHandler(tabs)
