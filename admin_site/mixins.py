from typing import Callable
from urllib.parse import urljoin

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.http.request import QueryDict
from django.http.response import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator

from admin_site.permissions import PlanContextPermissionPolicy
from aplans.context_vars import set_instance
from aplans.types import WatchAdminRequest
from aplans.utils import PlanRelatedModel


class SuccessUrlEditPageMixin:
    """After editing a model instance, redirect to the edit page again instead of the index page."""
    get_edit_url: Callable

    def get_success_url(self) -> str:
        return self.get_edit_url()

    def get_success_buttons(self) -> list:
        # Remove the button that takes the user to the edit view from the
        # success message, since we're redirecting back to the edit view already
        return []

    def get_breadcrumbs_items(self):
        # As the idea is to stay only on the edit page, hide the breadcrumb trail
        # that gives access e.g. to the index view
        return []


class SetInstanceMixin:
    def setup(self, *args, **kwargs):
        with set_instance(self.object):
            super().setup(*args, **kwargs)

    def dispatch(self, *args, **kwargs):
        with set_instance(self.object):
            return super().dispatch(*args, **kwargs)


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


class ContinueEditingMixin:
    request: WatchAdminRequest

    def continue_editing_active(self):
        return '_continue' in self.request.POST

    def get_success_url(self):
        if self.continue_editing_active():
            # Save and continue editing
            return self.get_edit_url()

        return super().get_success_url()

    def get_success_buttons(self):
        if self.continue_editing_active():
            # Save and continue editing -> No edit button required
            return []

        return super().get_success_buttons()


class PlanRelatedViewMixin:
    request: WatchAdminRequest

    def form_valid(self, form, *args, **kwargs):
        obj = form.instance
        if isinstance(obj, PlanRelatedModel):
            # Sanity check to ensure we're saving the model to a currently active
            # action plan.
            active_plan = self.request.user.get_active_admin_plan()
            plans = obj.get_plans()
            assert active_plan in plans

        return super().form_valid(form, *args, **kwargs)

    def dispatch(self, request: WatchAdminRequest, *args, **kwargs):
        user = request.user
        instance = getattr(self, 'object', None)
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


class ActivatePermissionHelperPlanContextMixin:
    @method_decorator(login_required)
    def dispatch(self, request: WatchAdminRequest, *args, **kwargs):
        """Set the plan context for permission helper before dispatching request."""

        if isinstance(self.permission_policy, PlanContextPermissionPolicy):
            with self.permission_policy.activate_plan_context(request.get_active_admin_plan()):
                ret = super().dispatch(request, *args, **kwargs)
                # We trigger render here, because the plan context is needed
                # still in the render stage.
                if hasattr(ret, 'render'):
                    ret = ret.render()
            return ret
        else:
            return super().dispatch(request, *args, **kwargs)
