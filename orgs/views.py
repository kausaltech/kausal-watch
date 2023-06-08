from django.contrib.admin.utils import unquote
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from wagtail.admin import messages
from wagtail.contrib.modeladmin.views import EditView, WMABaseView

from admin_site.wagtail import SetInstanceMixin
from admin_site.wagtail import AplansCreateView
from orgs.models import Organization


class OrganizationViewMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['parent_choices'] = Organization.objects.editable_by_user(self.request.user)
        # If the parent is not editable, the form would display an empty parent, leading to the org becoming a root when
        # saved. Prevent this by adding the parent to the queryset.
        if getattr(self, 'instance', None) and self.instance.get_parent():
            kwargs['parent_choices'] |= Organization.objects.filter(pk=self.instance.get_parent().pk)
        return kwargs


class CreateChildNodeView(OrganizationViewMixin, AplansCreateView):
    """View class that can take an additional URL param for parent id."""
    parent_pk = None

    def __init__(self, model_admin, parent_pk):
        self.parent_pk = unquote(parent_pk)
        object_qs = model_admin.model._default_manager.get_queryset()
        self.parent_instance = get_object_or_404(object_qs, pk=self.parent_pk)
        super().__init__(model_admin)

    def get_page_title(self):
        """Generate a title that explains you are adding a child."""
        title = super().get_page_title()
        return f'{title} child {self.opts.verbose_name} for {self.parent_instance}'

    def get_initial(self):
        """Set the selected parent field to the parent_pk."""
        return {'parent': self.parent_pk}


class OrganizationCreateView(OrganizationViewMixin, AplansCreateView):
    def form_valid(self, form):
        result = super().form_valid(form)
        # Add the new organization to the related organizations of the user's active plan
        org = form.instance
        plan = self.request.user.get_active_admin_plan()
        plan.related_organizations.add(org)
        return result


class OrganizationEditView(OrganizationViewMixin, SetInstanceMixin, EditView):
    pass


class SetOrganizationRelatedToActivePlanView(WMABaseView):
    page_title = gettext_lazy("Add organization to active plan")
    org_pk = None
    set_related = True
    template_name = 'aplans/confirmation.html'

    def __init__(self, model_admin, org_pk, set_related=True):
        self.org_pk = unquote(org_pk)
        self.org = get_object_or_404(Organization, pk=self.org_pk)
        self.set_related = set_related
        super().__init__(model_admin)

    def check_action_permitted(self, user):
        plan = user.get_active_admin_plan()
        return self.org.user_can_change_related_to_plan(user, plan)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.check_action_permitted(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_meta_title(self):
        plan = self.request.user.get_active_admin_plan()
        if self.set_related:
            msg = _("Confirm including %(org)s in plan %(plan)s")
        else:
            msg = _("Confirm excluding %(org)s from plan %(plan)s")
        return msg % {'org': self.org, 'plan': plan}

    def confirmation_message(self):
        plan = self.request.user.get_active_admin_plan()
        if self.set_related:
            msg = _("Do you really want to include the organization '%(org)s' in the plan '%(plan)s'?")
        else:
            msg = _("Do you really want to exclude the organization '%(org)s' from the plan '%(plan)s'?")
        return msg % {'org': self.org, 'plan': plan}

    def add_to_plan(self, plan):
        if self.org.pk in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_("The organization is already included in the plan"))
        plan.related_organizations.add(self.org)

    def remove_from_plan(self, plan):
        if self.org.pk not in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_("The organization is not included in the plan"))
        plan.related_organizations.remove(self.org)

    def post(self, request, *args, **kwargs):
        plan = request.user.get_active_admin_plan()
        try:
            if self.set_related:
                self.add_to_plan(plan)
            else:
                self.remove_from_plan(plan)
        except ValueError as e:
            messages.error(request, e)
            return redirect(self.index_url)
        if self.set_related:
            msg = _("Organization '%(org)s' has been included in plan '%(plan)s'.")
        else:
            msg = _("Organization '%(org)s' has been excluded from plan '%(plan)s'.")
        messages.success(request, msg % {'org': self.org, 'plan': plan})
        return redirect(self.index_url)
