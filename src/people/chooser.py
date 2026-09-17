from __future__ import annotations

from wagtail import hooks
from wagtail.search.backends import get_search_backend

from kausal_common.people.chooser import (
    PersonChooser,
    PersonChooserMixin as BasePersonChooserMixin,
    PersonChooserViewSet as BasePersonChooserViewSet,
    PersonModelChooserCreateTabMixin as BasePersonModelChooserCreateTabMixin,
)
from kausal_common.users import user_or_bust


class PersonChooserMixin(BasePersonChooserMixin):
    def get_object_list(self, search_term=None, **kwargs):
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        object_list = self.get_unfiltered_object_list().available_for_plan(plan)

        # Workaround to prevent Wagtail from looking for `path` (from Organization) in the search fields for Person
        object_list = self.model.objects.filter(id__in=object_list)  # type: ignore[attr-defined]

        if search_term:
            search_backend = get_search_backend()
            object_list = search_backend.autocomplete(search_term, object_list)

        return object_list


class PersonModelChooserCreateTabMixin(BasePersonModelChooserCreateTabMixin):
    def get_initial(self):
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        return {'organization': plan.organization}


class TaskPersonChooserMixin(PersonChooserMixin):
    """
    Person chooser that also offers the plan's contact persons from unrelated organizations.

    Task assignment has to reach people like external consultants, who are contact persons for an action in
    this plan but belong to no organization related to it. Widening `PersonChooserMixin` itself would change
    the four other fields that share it (action and indicator contact persons, organization plan admins,
    plan general admins), so the wider list lives here.
    """

    def get_object_list(self, search_term=None, **kwargs):
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        object_list = self.get_unfiltered_object_list().available_for_plan(plan, include_contact_persons=True)

        # Same workaround as in `PersonChooserMixin`: keep Wagtail from searching Organization's `path`.
        object_list = self.model.objects.filter(id__in=object_list)  # type: ignore[attr-defined]

        if search_term:
            search_backend = get_search_backend()
            object_list = search_backend.autocomplete(search_term, object_list)

        return object_list


class PersonChooserViewSet(BasePersonChooserViewSet):
    chooser_mixin_class = PersonChooserMixin
    create_tab_mixin_class = PersonModelChooserCreateTabMixin


class TaskPersonChooserViewSet(BasePersonChooserViewSet):
    chooser_mixin_class = TaskPersonChooserMixin
    create_tab_mixin_class = PersonModelChooserCreateTabMixin


class TaskPersonChooser(PersonChooser):
    """`PersonChooser` bound to the wider task-assignment person list."""

    choose_modal_url_name = 'task_person_chooser:choose'


@hooks.register('register_admin_viewset')
def register_watch_person_chooser_viewset():
    return PersonChooserViewSet('person_chooser', url_prefix='person-chooser')


@hooks.register('register_admin_viewset')
def register_task_person_chooser_viewset():
    return TaskPersonChooserViewSet('task_person_chooser', url_prefix='task-person-chooser')
