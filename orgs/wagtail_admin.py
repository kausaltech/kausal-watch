# Parts adapted from https://posts-by.lb.ee/building-a-configurable-taxonomy-in-wagtail-django-94ca1080fb28
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.urls import URLPattern, path, re_path
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from wagtail.admin.panels import FieldPanel, ObjectList, TabbedInterface
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from wagtail_modeladmin.helpers import ButtonHelper, PermissionHelper
from wagtail_modeladmin.options import ModelAdmin
from wagtailgeowidget import __version__ as wagtailgeowidget_version

from kausal_common.models.permission_policy import ModelPermissionPolicy, ObjectSpecificAction

from aplans.extensions import modeladmin_register

from admin_site.panels import TranslatedFieldPanel
from admin_site.utils import admin_req
from admin_site.wagtail import CondensedInlinePanel
from people.chooser import PersonChooser
from users.models import User

from .forms import NodeForm
from .models import Organization, OrganizationMetadataAdmin
from .views import (
    CreateChildNodeView,
    CreateChildNodeViewOld,
    OrganizationCreateView,
    OrganizationCreateViewOld,
    OrganizationDeleteView,
    OrganizationDeleteViewOld,
    OrganizationEditView,
    OrganizationEditViewOld,
    OrganizationIndexView,
    SetOrganizationRelatedToActivePlanView,
    SetOrganizationRelatedToActivePlanViewOld,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Q
    from wagtail.admin.menu import MenuItem
    from wagtail.admin.panels.base import Panel


if int(wagtailgeowidget_version.split('.')[0]) >= 7:
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
            start=self.edit_button_classnames,
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude'),
        )
        return {
            'classname': classnames,
            'label': _("Add child"),
            'title': _("Add child under this node"),
            'icon': 'plus',
            'url': self.url_helper.get_action_url('add_child', quote(pk)),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)

        add_child_button = self.add_child_button(
            pk=getattr(obj, self.opts.pk.attname),
            **kwargs,
        )
        user = self.request.user
        plan = user.get_active_admin_plan()
        if not user.is_general_admin_for_plan(plan):
            # TODO: allow for organization metadata admins
            # but without the huge amount of db queries
            # that iterating org.user_can_edit entails
            return buttons
        buttons.append(add_child_button)

        return buttons


class NodeAdmin(ModelAdmin):
    button_helper_class = NodeButtonHelper
    panels = [
        TranslatedFieldPanel('name'),
    ]

    def add_child_view(self, request, instance_pk):
        """Generate a class-based view to provide 'add child' functionality."""
        # instance_pk will become the default selected parent_pk
        # TODO: Since CreateChildNodeView is a CreateView, it checks for user_can_create permissions. However, when
        # adding a child, we also should check that the user has permissions for the parent of the new instance.
        return CreateChildNodeViewOld.as_view(model_admin=self, parent_pk=instance_pk)(request)

    def get_admin_urls_for_registration(self):
        """Add the new url for add child page to the registered URLs."""
        urls = super().get_admin_urls_for_registration()
        add_child_url = re_path(
            self.url_helper.get_action_url_pattern('add_child'),
            self.add_child_view,
            name=self.url_helper.get_action_url_name('add_child'),
        )
        return urls + (add_child_url,)


class NodeViewSet(SnippetViewSet):
    """ViewSet that provides fundamentals for Node-based models."""

    list_display = ['name', 'parent']
    add_child_url_name = 'add_child'

    panels = [
        TranslatedFieldPanel('name'),
    ]

    @property
    def add_child_view(self):
        """Generate a class-based view to provide 'add child' functionality."""
        return self.construct_view(CreateChildNodeView, **self.get_add_view_kwargs())

    def get_urlpatterns(self) -> list[URLPattern]:
        urls =  super().get_urlpatterns()
        add_child_url = path(
            route=f'{self.add_child_url_name}/<str:parent_pk>/',
            view=self.add_child_view,
            name=self.add_child_url_name,
        )
        return urls + [add_child_url]

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(
            add_child_url_name=self.get_url_name(self.add_child_url_name),
            **kwargs,
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


class OrganizationPermissionPolicy(ModelPermissionPolicy):

    def user_has_permission(self, user: User | AnonymousUser, action: str) -> bool:
        assert isinstance(user, User)

        if user.is_superuser:
            return True
        if action == 'view':
            return True
        # TODO: The following is the old logic, which we may reinstate when we
        # thought about how to handle permissions best.
        # person = user.get_corresponding_person()
        # return person and person.metadata_adminable_organizations.exists()
        # For now we allow general admins (for any plan) to create organizations.
        if action == 'add':
            return user.is_general_admin_for_plan()
        # We cannot know if the user has other permissions to the instance
        # without knowing the instance. user_has_permission should be overridden
        # in relevant places to call user_has_permission_for_instance
        return False

    def user_has_permission_for_instance(self, user: User | AnonymousUser, action: str, instance: Organization) -> bool:
        assert isinstance(user, User)

        if user.is_superuser:
            return True

        if action == 'view':
            return True
        if action in ('change', 'delete'):
            return instance.user_can_edit(user)
        if action == 'add':
            return user.is_general_admin_for_plan()
        if action == SetOrganizationRelatedToActivePlanView.permission_required:
            plan = user.get_active_admin_plan()
            return instance.user_can_change_related_to_plan(user, plan)

        return super().user_has_permission_for_instance(user, action, instance)

    def anon_has_perm(self, action: ObjectSpecificAction, obj: Any) -> bool:
        raise NotImplementedError

    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        raise NotImplementedError

    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        raise NotImplementedError

    def user_can_create(self, user: User, context: Any) -> bool:
        raise NotImplementedError

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: Any) -> bool:
        raise NotImplementedError


class OrganizationForm(NodeForm):
    def __init__(self, *args, **kwargs):
        modeladmin_user = kwargs.pop('user', None)
        viewset_user = kwargs.get('for_user')
        self.user = modeladmin_user or viewset_user
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


class InvisiblePlanPanel(FieldPanel):
    """
    Panel that adds a hidden plan field to the form.

    The value is set to the user's active plan.
    """

    class BoundPanel(FieldPanel.BoundPanel):

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.attrs.update({'hidden': 'true'})
            user = admin_req(self.request).user
            self.form.initial['plan'] = user.get_active_admin_plan()


class OrganizationButtonHelper(NodeButtonHelper):
    def add_child_button(self, pk, **kwargs):
        result = super().add_child_button(pk, **kwargs)
        result['label'] = _("Add suborganization")
        result['title'] = _("Add suborganization under this organization")
        return result

    def include_organization_in_active_plan_button(self, pk, **kwargs):
        classnames = self.prepare_classnames(
            start=self.edit_button_classnames,
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude'),
        )
        return {
            'classname': classnames,
            'label': _("Include in plan"),
            'title': _("Include this organization in the active plan"),
            'icon': 'link',
            'url': self.url_helper.get_action_url('include_organization_in_active_plan', quote(pk)),
        }

    def exclude_organization_from_active_plan_button(self, pk, **kwargs):
        classnames = self.prepare_classnames(
            start=self.edit_button_classnames,
            add=kwargs.get('classnames_add'),
            exclude=kwargs.get('classnames_exclude'),
        )
        return {
            'classname': classnames,
            'label': _("Exclude from plan"),
            'title': _("Exclude this organization from the active plan"),
            'icon': 'fontawesome-link-slash',
            'url': self.url_helper.get_action_url('exclude_organization_from_active_plan', quote(pk)),
        }

    def get_buttons_for_obj(self, obj: Organization, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)

        # Show "include in / exclude from active plan" button if user has permission and it's a root organization
        plan = self.request.user.get_active_admin_plan()
        if obj.user_can_change_related_to_plan(self.request.user, plan) and obj.is_root():
            # FIXME: Duplicates a check in IncludeOrganizationInActivePlanView
            if obj.pk in plan.related_organizations.values_list('pk', flat=True):
                exclude_organization_from_active_plan_button = self.exclude_organization_from_active_plan_button(
                    pk=getattr(obj, self.opts.pk.attname),
                    **kwargs,
                )
                buttons.append(exclude_organization_from_active_plan_button)
            else:
                include_organization_in_active_plan_button = self.include_organization_in_active_plan_button(
                    pk=getattr(obj, self.opts.pk.attname),
                    **kwargs,
                )
                buttons.append(include_organization_in_active_plan_button)

        return buttons


@modeladmin_register
class OrganizationAdmin(NodeAdmin):
    model = Organization
    menu_label = _("Organizations")
    menu_icon = 'kausal-organization'
    menu_order = 220
    button_helper_class = OrganizationButtonHelper
    permission_helper_class = OrganizationPermissionHelper
    create_view_class = OrganizationCreateViewOld
    edit_view_class = OrganizationEditViewOld
    delete_view_class = OrganizationDeleteViewOld
    search_fields = ('name', 'abbreviation')
    list_display = ('name', 'abbreviation')

    basic_panels = NodeAdmin.panels + [
        FieldPanel(
            # virtual field, needs to be specified in the form
            'parent', heading=pgettext_lazy('organization', 'Parent'),
        ),
        FieldPanel('logo'),
        TranslatedFieldPanel('abbreviation'),
        FieldPanel('internal_abbreviation'),
        # Don't allow editing identifiers at this point
        # CondensedInlinePanel('identifiers', panels=[
        #     FieldPanel('namespace'),
        #     FieldPanel('identifier'),
        # ]),
        FieldPanel('description'),
        FieldPanel('url'),
        FieldPanel('email'),
        FieldPanel('primary_language', read_only=True),  # read-only for now because changes could cause trouble
        GoogleMapsPanel('location', permission='superuser'),
    ]

    permissions_panels = [
        CondensedInlinePanel(
            'organization_plan_admins',
            panels=[
                InvisiblePlanPanel('plan'),
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

    def include_organization_in_active_plan_view(self, request, instance_pk):
        return SetOrganizationRelatedToActivePlanViewOld.as_view(
            model_admin=self,
            org_pk=instance_pk,
            set_related=True,
        )(request)

    def exclude_organization_from_active_plan_view(self, request, instance_pk):
        return SetOrganizationRelatedToActivePlanViewOld.as_view(
            model_admin=self,
            org_pk=instance_pk,
            set_related=False,
        )(request)

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        include_organization_in_active_plan_url = re_path(
            self.url_helper.get_action_url_pattern('include_organization_in_active_plan'),
            self.include_organization_in_active_plan_view,
            name=self.url_helper.get_action_url_name('include_organization_in_active_plan'),
        )
        exclude_organization_from_active_plan_url = re_path(
            self.url_helper.get_action_url_pattern('exclude_organization_from_active_plan'),
            self.exclude_organization_from_active_plan_view,
            name=self.url_helper.get_action_url_name('exclude_organization_from_active_plan'),
        )
        return urls + (
            include_organization_in_active_plan_url,
            exclude_organization_from_active_plan_url,
        )

    def get_edit_handler(self):
        tabs = [
            ObjectList(self.basic_panels, heading=_('Basic information')),
            ObjectList(self.permissions_panels, heading=_('Permissions')),
        ]
        return TabbedInterface(tabs, base_form_class=OrganizationForm)

class OrganizationViewSet(NodeViewSet):
    model = Organization
    menu_label = _("WIP Organizations")
    icon = 'kausal-organization'
    menu_order = 220
    permission_policy = OrganizationPermissionPolicy(model)
    index_view_class = OrganizationIndexView
    create_view_class = OrganizationCreateView
    edit_view_class = OrganizationEditView
    delete_view_class = OrganizationDeleteView
    search_fields = ['name', 'abbreviation']
    list_display = NodeViewSet.list_display + ['abbreviation']
    add_to_admin_menu = True
    include_organization_in_active_plan_url_name = 'include_organization_in_active_plan'
    exclude_organization_from_active_plan_url_name = 'exclude_organization_from_active_plan'

    basic_panels = NodeViewSet.panels + [
        FieldPanel(
            # virtual field, needs to be specified in the form
            'parent', heading=pgettext_lazy('organization', 'Parent'),
        ),
        FieldPanel('logo'),
        TranslatedFieldPanel('abbreviation'),
        FieldPanel('internal_abbreviation'),
        # Don't allow editing identifiers at this point
        # CondensedInlinePanel('identifiers', panels=[
        #     FieldPanel('namespace'),
        #     FieldPanel('identifier'),
        # ]),
        FieldPanel('description'),
        FieldPanel('url'),
        FieldPanel('email'),
        FieldPanel('primary_language', read_only=True),  # read-only for now because changes could cause trouble
        GoogleMapsPanel('location', permission='superuser'),
    ]

    permissions_panels: list[Panel] = [
        CondensedInlinePanel(
            'organization_plan_admins',
            panels=[
                InvisiblePlanPanel('plan'),
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

    @property
    def include_organization_in_active_plan_view(self):
        return self.construct_view(SetOrganizationRelatedToActivePlanView, set_related=True)

    @property
    def exclude_organization_from_active_plan_view(self):
        return self.construct_view(SetOrganizationRelatedToActivePlanView, set_related=False)

    # FIXME: As of writing this the Wagtail version (6.1.X) we use has a bug
    # which only shows the menu item when user has "add", "change" or "delete"
    # permission, while "view" should be enough. (See
    # https://github.com/wagtail/wagtail/blob/747d70e0656b86e3e8c8d123ecae82fa61cd1438/wagtail/admin/viewsets/model.py#L521C16-L521C58
    # for the specific line of code). This seems to be fixed version 6.2.X
    # forward, so when upgraded to Wagtail 6.2.X this workaround should be safe
    # to delete.
    def get_menu_item(self, order: int | None = None) -> MenuItem:
        menu_item = super().get_menu_item(order)
        menu_item.is_shown = lambda request: True  # noqa: ARG005
        return menu_item

    def get_urlpatterns(self) -> list[URLPattern]:
        urls =  super().get_urlpatterns()
        include_organization_in_active_plan_url = path(
            route=f'{self.include_organization_in_active_plan_url_name}/<str:pk>/',
            view=self.include_organization_in_active_plan_view,
            name=self.include_organization_in_active_plan_url_name,
        )
        exclude_organization_from_active_plan_url = path(
            route=f'{self.exclude_organization_from_active_plan_url_name}/<str:pk>/',
            view=self.exclude_organization_from_active_plan_view,
            name=self.exclude_organization_from_active_plan_url_name,
        )
        return urls + [
            include_organization_in_active_plan_url,
            exclude_organization_from_active_plan_url,
        ]

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(
            include_organization_in_active_plan_url_name=self.get_url_name(self.include_organization_in_active_plan_url_name),
            exclude_organization_from_active_plan_url_name=self.get_url_name(self.exclude_organization_from_active_plan_url_name),
            **kwargs,
        )

    def get_edit_handler(self):
        tabs = [
            ObjectList(self.basic_panels, heading=_('Basic information')),
            ObjectList(self.permissions_panels, heading=_('Permissions')),
        ]
        return TabbedInterface(tabs, base_form_class=OrganizationForm).bind_to_model(self.model)


# Extended version is registered in kausal-extensions
register_snippet(OrganizationViewSet)
