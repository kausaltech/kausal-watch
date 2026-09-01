from __future__ import annotations

from typing import TYPE_CHECKING

from django import forms
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.forms.choosers import BaseFilterForm

from kausal_common.admin_site.choosers import ChooserViewSet

from .models import Organization

if TYPE_CHECKING:
    from wagtail.admin.views.generic.chooser import ChooseResultsView, ChooseView

    from orgs.models import OrganizationQuerySet


class OrganizationFilterForm(BaseFilterForm):
    """
    Filter form that does simple icontains search instead of using the Wagtail search backend.

    The default SearchFilterMixin uses the search backend which cannot handle
    the depth filter from get_root_nodes(). We do the filtering ourselves in
    get_object_list instead.
    """

    q = forms.CharField(
        label=_('Search term'),
        widget=forms.TextInput(attrs={'placeholder': _('Search')}),
        required=False,
    )


class OrganizationChooserViewSet(ChooserViewSet[Organization]):
    """
    Chooser for selecting top-level organizations.

    Used by superusers when creating new plans. Only shows root-level
    organizations. Organization creation is handled by the plan creation
    form instead.
    """

    model = Organization
    icon = 'kausal-organization'
    choose_one_text = _('Choose an organization')
    choose_another_text = _('Choose another organization')
    per_page = 30
    preserve_url_parameters = ['multiple']

    @property
    def choose_view(self):
        view_class = self.inject_view_methods(self.choose_view_class, ['get_object_list'])
        return self.construct_view(
            view_class,
            icon=self.icon,
            page_title=self.page_title,
            filter_form_class=OrganizationFilterForm,
        )

    @property
    def choose_results_view(self):
        view_class = self.inject_view_methods(self.choose_results_view_class, ['get_object_list'])
        return self.construct_view(view_class, filter_form_class=OrganizationFilterForm)

    def get_object_list(self, view: ChooseView | ChooseResultsView | None) -> OrganizationQuerySet:
        objs = Organization.get_root_nodes()
        if view is not None:
            search_term = view.request.GET.get('q')
            if search_term:
                objs = objs.filter(name__icontains=search_term)
        return objs


organization_chooser_viewset = OrganizationChooserViewSet('organization_chooser', url_prefix='organization-chooser')


@hooks.register('register_admin_viewset')
def register_organization_chooser_viewset():
    return organization_chooser_viewset
