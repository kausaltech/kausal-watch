from __future__ import annotations

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.urls import NoReverseMatch, reverse
from wagtail.admin.menu import admin_menu, settings_menu
from wagtail.admin.panels import FieldPanel, FieldRowPanel, MultiFieldPanel

import pytest

from aplans.cache import PlanSpecificCache
from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.models import Action
from actions.tests.factories import PlanFactory
from admin_site.built_in_field_customization_admin import (
    BuiltInFieldCustomizationForm,
    BuiltInFieldCustomizationViewSet,
)
from admin_site.field_customization import (
    collect_customizable_field_names,
    get_customizable_models,
    get_field_choices,
    make_field_choice_value,
    register_customizable_fields,
)
from admin_site.models import BuiltInFieldCustomization
from admin_site.tests.factories import BuiltInFieldCustomizationFactory, ClientPlanFactory
from admin_site.wagtail import CustomizableBuiltInFieldPanel, CustomizableBuiltInPlanFilteredFieldPanel
from indicators.models import Indicator

pytestmark = pytest.mark.django_db

LIST_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:list'
ADD_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:add'
EDIT_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:edit'
DELETE_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:delete'
HISTORY_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:history'
USAGE_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:usage'
HISTORY_RESULTS_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:history_results'
COMPARE_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:revisions_compare'
COPY_URL_NAME = 'wagtailsnippets_admin_site_builtinfieldcustomization:copy'
MENU_LABEL = 'Field customizations'


def _post_data(**overrides):
    data = {
        'field': make_field_choice_value(Action, 'identifier'),
        'label_override': '',
        'help_text_override': '',
        'instances_visible_for': InstancesVisibleForMixin.VisibleFor.PUBLIC,
        'instances_editable_by': InstancesEditableByMixin.EditableBy.AUTHENTICATED,
    }
    data.update(overrides)
    return data


@pytest.fixture
def other_plan_customization():
    return BuiltInFieldCustomizationFactory.create(plan=PlanFactory.create(), field_name='identifier')


@pytest.fixture
def admin_client(client, plan, plan_admin_user):
    ClientPlanFactory.create(plan=plan)
    client.force_login(plan_admin_user)
    return client


def test_plan_admin_can_open_the_index(admin_client):
    response = admin_client.get(reverse(LIST_URL_NAME))
    assert response.status_code == 200


def test_contact_person_cannot_open_the_index(client, action, action_contact_person_user):
    ClientPlanFactory.create(plan=action.plan)
    client.force_login(action_contact_person_user)
    response = client.get(reverse(LIST_URL_NAME))
    assert response.status_code == 302
    assert response.url.startswith('/admin/')


def test_contact_person_cannot_open_the_add_view(client, action, action_contact_person_user):
    ClientPlanFactory.create(plan=action.plan)
    client.force_login(action_contact_person_user)
    response = client.get(reverse(ADD_URL_NAME))
    assert response.status_code == 302


def test_create_sets_plan_content_type_and_field_name(admin_client, plan):
    response = admin_client.post(
        reverse(ADD_URL_NAME),
        data=_post_data(label_override='Code', instances_editable_by=InstancesEditableByMixin.EditableBy.PLAN_ADMINS),
    )
    assert response.status_code == 302
    customization = BuiltInFieldCustomization.objects.get()
    assert customization.plan == plan
    assert customization.content_type == ContentType.objects.get_for_model(Action)
    assert customization.field_name == 'identifier'
    assert customization.label_override == 'Code'
    assert customization.instances_editable_by == InstancesEditableByMixin.EditableBy.PLAN_ADMINS


def test_create_rejects_a_field_that_is_not_customizable(admin_client):
    response = admin_client.post(reverse(ADD_URL_NAME), data=_post_data(field='actions.action:i_do_not_exist'))
    assert response.status_code == 200
    assert 'field' in response.context['form'].errors
    assert not BuiltInFieldCustomization.objects.exists()


def test_create_rejects_a_duplicate_customization(admin_client, plan):
    BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='identifier',
    )
    response = admin_client.post(reverse(ADD_URL_NAME), data=_post_data())
    assert response.status_code == 200
    assert 'field' in response.context['form'].errors
    assert BuiltInFieldCustomization.objects.count() == 1


def test_the_same_field_may_be_customized_in_another_plan(admin_client, plan):
    BuiltInFieldCustomizationFactory.create(
        plan=PlanFactory.create(),
        content_type=ContentType.objects.get_for_model(Action),
        field_name='identifier',
    )
    response = admin_client.post(reverse(ADD_URL_NAME), data=_post_data())
    assert response.status_code == 302
    assert BuiltInFieldCustomization.objects.filter(plan=plan).count() == 1


def test_edit_keeps_the_customization_unique(admin_client, plan):
    BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='identifier',
    )
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='name',
    )
    url = reverse(EDIT_URL_NAME, args=[customization.pk])

    # Editing without changing the field must be accepted...
    response = admin_client.post(url, data=_post_data(field=make_field_choice_value(Action, 'name')))
    assert response.status_code == 302

    # ...but moving it onto a field that is already customized must not.
    response = admin_client.post(url, data=_post_data(field=make_field_choice_value(Action, 'identifier')))
    assert response.status_code == 200
    assert 'field' in response.context['form'].errors


def test_edit_view_preselects_the_customized_field(admin_client, plan):
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='identifier',
    )
    response = admin_client.get(reverse(EDIT_URL_NAME, args=[customization.pk]))
    assert response.status_code == 200
    assert response.context['form'].initial['field'] == make_field_choice_value(Action, 'identifier')


def test_index_only_lists_customizations_of_the_active_plan(admin_client, plan):
    own = BuiltInFieldCustomizationFactory.create(plan=plan, field_name='identifier')
    other = BuiltInFieldCustomizationFactory.create(plan=PlanFactory.create(), field_name='identifier')
    response = admin_client.get(reverse(LIST_URL_NAME))
    listed = list(response.context['object_list'])
    assert own in listed
    assert other not in listed


def test_a_customization_of_another_plan_cannot_be_edited(admin_client, other_plan_customization):
    """A POST must leave the object untouched, not merely redirect the GET."""
    before = other_plan_customization.label_override
    response = admin_client.post(
        reverse(EDIT_URL_NAME, args=[other_plan_customization.pk]),
        data=_post_data(label_override='hijacked'),
    )
    assert response.status_code != 200 or response.context['form'].errors
    other_plan_customization.refresh_from_db()
    assert other_plan_customization.label_override == before


def test_a_customization_of_another_plan_cannot_be_deleted(admin_client, other_plan_customization):
    response = admin_client.post(reverse(DELETE_URL_NAME, args=[other_plan_customization.pk]))
    # Wagtail turns the PermissionDenied into a redirect; asserting `!= 200` would also pass on a 500.
    assert response.status_code == 302
    assert BuiltInFieldCustomization.objects.filter(pk=other_plan_customization.pk).exists()


@pytest.mark.parametrize('url_name', [HISTORY_URL_NAME, USAGE_URL_NAME, HISTORY_RESULTS_URL_NAME])
def test_a_customization_of_another_plan_is_not_readable(admin_client, other_plan_customization, url_name):
    response = admin_client.get(reverse(url_name, args=[other_plan_customization.pk]))
    assert response.status_code == 302


def test_revisions_of_another_plan_cannot_be_compared(admin_client, other_plan_customization):
    other_plan_customization.save_revision()
    other_plan_customization.label_override = 'changed'
    other_plan_customization.save()
    other_plan_customization.save_revision()
    revisions = list(other_plan_customization.revisions.order_by('pk').values_list('pk', flat=True))
    url = reverse(COMPARE_URL_NAME, args=[other_plan_customization.pk, revisions[0], revisions[1]])
    assert admin_client.get(url).status_code == 302


def test_copying_is_disabled(admin_client, plan):
    """
    Wagtail's copy view bypasses `WatchCreateView`, so it would neither set the plan nor check it.

    Copying is meaningless for this model anyway: `(plan, content_type, field_name)` is unique, so
    every copy within the plan is an immediate duplicate.
    """
    customization = BuiltInFieldCustomizationFactory.create(plan=plan, field_name='identifier')
    with pytest.raises(NoReverseMatch):
        reverse(COPY_URL_NAME, args=[customization.pk])
    assert '/copy/' not in admin_client.get(reverse(LIST_URL_NAME)).content.decode()


def test_submitting_without_a_field_reports_a_form_error(admin_client, plan):
    """A missing field must not reach the model's validation, which reports errors on `field_name`."""
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='identifier',
    )
    response = admin_client.post(reverse(EDIT_URL_NAME, args=[customization.pk]), data=_post_data(field=''))
    assert response.status_code == 200
    assert 'field' in response.context['form'].errors


def test_field_choices_cover_the_customizable_models():
    values = {value for _group, choices in get_field_choices() for value, _label in choices}
    assert make_field_choice_value(Action, 'identifier') in values
    assert make_field_choice_value(Action, 'tasks') in values
    assert make_field_choice_value(Indicator, 'name') in values
    # `level` is a form-only field on the indicator form, so it must not be offered.
    assert 'indicators.indicator:level' not in values


def _menu_item_is_shown(rf, user) -> bool:
    request = rf.get('/admin/')
    request.user = user
    return BuiltInFieldCustomizationViewSet().get_menu_item().is_shown(request)


def test_menu_item_is_shown_for_plan_admin(rf, plan, plan_admin_user):
    assert _menu_item_is_shown(rf, plan_admin_user) is True


def test_menu_item_is_shown_for_superuser(rf, plan, superuser):
    assert _menu_item_is_shown(rf, superuser) is True


def test_menu_item_is_hidden_for_contact_person(rf, action, action_contact_person_user):
    assert _menu_item_is_shown(rf, action_contact_person_user) is False


def _menu_request(rf, user, plan):
    request = rf.get('/admin/')
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=plan)
    request.get_active_admin_plan = lambda: plan
    return request


def test_menu_item_lives_in_the_settings_menu(rf, plan, plan_admin_user):
    request = _menu_request(rf, plan_admin_user, plan)
    assert MENU_LABEL in [str(item.label) for item in settings_menu.menu_items_for_request(request)]
    assert MENU_LABEL not in [str(item.label) for item in admin_menu.menu_items_for_request(request)]


def test_menu_item_follows_the_attribute_type_items(rf, plan, plan_admin_user):
    """It belongs with the other field configuration, after "Fields (Action)" and "Fields (Category)"."""
    request = _menu_request(rf, plan_admin_user, plan)
    items = sorted(settings_menu.menu_items_for_request(request), key=lambda item: item.order)
    labels = [str(item.label) for item in items]
    assert labels.index('Fields (Action)') < labels.index(MENU_LABEL)
    assert labels.index('Fields (Category)') < labels.index(MENU_LABEL)
    assert labels.index(MENU_LABEL) < labels.index('Category types')


def test_add_view_renders_one_grouped_field_widget(admin_client):
    """The customized field is picked with a single widget; the model fields behind it are derived."""
    response = admin_client.get(reverse(ADD_URL_NAME))
    assert response.status_code == 200
    html = response.content.decode()
    assert '<optgroup label="Action">' in html
    assert 'value="actions.action:identifier"' in html
    assert 'name="content_type"' not in html
    assert 'name="field_name"' not in html


def test_index_shows_the_field_label_and_is_searchable(admin_client, plan):
    content_type = ContentType.objects.get_for_model(Action)
    BuiltInFieldCustomizationFactory.create(plan=plan, content_type=content_type, field_name='primary_org')
    BuiltInFieldCustomizationFactory.create(plan=plan, content_type=content_type, field_name='identifier')
    url = reverse(LIST_URL_NAME)

    response = admin_client.get(url)
    assert 'Primary organization' in response.content.decode()

    response = admin_client.get(url, data={'q': 'primary_org'})
    assert [c.field_name for c in response.context['object_list']] == ['primary_org']


def test_editing_a_customization_of_a_vanished_field_reports_a_form_error(admin_client, plan):
    """
    A stale `field_name` must surface as a form error rather than an exception.

    The model reports such errors on `field_name`, which is not a form field of its own, so the form
    has to remap them onto the `field` widget.
    """
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='field_that_no_longer_exists',
    )
    response = admin_client.post(reverse(EDIT_URL_NAME, args=[customization.pk]), data=_post_data(field=''))
    assert response.status_code == 200
    assert 'field' in response.context['form'].errors


def test_index_survives_a_customization_of_a_vanished_field(admin_client, plan):
    """One stale customization must not make the whole listing unrenderable."""
    BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='field_that_no_longer_exists',
    )
    response = admin_client.get(reverse(LIST_URL_NAME))
    assert response.status_code == 200
    assert 'Field that no longer exists' in response.content.decode()


def test_content_type_filter_only_offers_registered_models(admin_client, plan):
    BuiltInFieldCustomizationFactory.create(plan=plan, field_name='identifier')
    response = admin_client.get(reverse(LIST_URL_NAME))
    choices = list(response.context['filters'].filters['content_type'].field.choices)
    labels = {str(label) for _value, label in choices}
    assert 'Action' in labels
    # An unrestricted queryset would offer every content type in the installation.
    assert 'Page' not in labels
    assert len(choices) == len(get_customizable_models()) + 1  # +1 for the empty choice


def test_a_customization_of_an_unregistered_but_existing_field_stays_editable(admin_client, plan):
    """
    A customization created outside the admin may target a field that was never registered.

    It must remain editable, otherwise its label cannot be changed without re-pointing it at a
    different field.
    """
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='internal_notes',
    )
    url = reverse(EDIT_URL_NAME, args=[customization.pk])

    response = admin_client.get(url)
    assert response.status_code == 200
    assert response.context['form'].initial['field'] == make_field_choice_value(Action, 'internal_notes')

    response = admin_client.post(
        url,
        data=_post_data(field=make_field_choice_value(Action, 'internal_notes'), label_override='Notes'),
    )
    assert response.status_code == 302
    customization.refresh_from_db()
    assert customization.field_name == 'internal_notes'
    assert customization.label_override == 'Notes'


def test_collect_customizable_field_names_descends_into_nested_panels():
    panels = [
        CustomizableBuiltInFieldPanel('name'),
        FieldPanel('not_customizable'),
        MultiFieldPanel([
            CustomizableBuiltInFieldPanel('identifier'),
            FieldRowPanel([
                CustomizableBuiltInPlanFilteredFieldPanel('status'),
                CustomizableBuiltInFieldPanel('name'),  # duplicate, must be collected once
            ]),
        ]),
    ]
    assert collect_customizable_field_names(panels) == ['name', 'identifier', 'status']


def test_registering_an_unknown_field_fails_loudly():
    with pytest.raises(ImproperlyConfigured, match='not a valid field'):
        register_customizable_fields(Action, ['definitely_not_a_field'])


def test_content_type_filter_is_ordered_by_verbose_name(admin_client, plan):
    BuiltInFieldCustomizationFactory.create(plan=plan, field_name='identifier')
    response = admin_client.get(reverse(LIST_URL_NAME))
    choices = list(response.context['filters'].filters['content_type'].field.choices)
    labels = [str(label) for _value, label in choices][1:]  # drop the empty choice
    assert labels == sorted(labels, key=str.lower)


def test_an_unregistered_field_is_merged_into_its_model_group(plan):
    """The extra option must extend the model's existing group, not add a second one with its name."""
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='internal_notes',
    )
    form = BuiltInFieldCustomizationForm(instance=customization, plan=plan)
    field_choice = form.fields['field']
    assert isinstance(field_choice, forms.ChoiceField)
    # `choices` is declared as a wide union that also covers callables and mappings
    choices = field_choice.choices
    assert isinstance(choices, list)
    groups = [group for group, _options in choices]
    assert len(groups) == len(set(groups))

    action_options = next(options for group, options in choices if group == 'Action')
    values = [value for value, _label in action_options]
    assert make_field_choice_value(Action, 'internal_notes') in values
    assert make_field_choice_value(Action, 'identifier') in values


@pytest.fixture
def stale_customization(plan):
    """Build a customization whose model no longer exists, e.g. after an app was removed."""
    content_type = ContentType.objects.create(app_label='gone_app', model='gonemodel')
    return BuiltInFieldCustomizationFactory.create(plan=plan, content_type=content_type, field_name='whatever')


def test_a_customization_of_a_vanished_model_is_still_displayable(stale_customization):
    """`str()` and `field_label` must degrade rather than assert, or they take the listing down."""
    assert stale_customization.field_label == 'Whatever'
    assert 'gone_app | gonemodel' in str(stale_customization)


def test_index_and_edit_survive_a_customization_of_a_vanished_model(admin_client, stale_customization):
    assert admin_client.get(reverse(LIST_URL_NAME)).status_code == 200
    assert admin_client.get(reverse(EDIT_URL_NAME, args=[stale_customization.pk])).status_code == 200


def test_a_customization_of_a_vanished_model_fails_validation(stale_customization):
    """Saving one must raise a ValidationError the form can render, not an AssertionError."""
    with pytest.raises(ValidationError):
        stale_customization.full_clean()


def test_a_customization_of_a_vanished_model_can_be_repointed(admin_client, stale_customization):
    response = admin_client.post(
        reverse(EDIT_URL_NAME, args=[stale_customization.pk]),
        data=_post_data(label_override='fixed'),
    )
    assert response.status_code == 302
    stale_customization.refresh_from_db()
    assert stale_customization.content_type == ContentType.objects.get_for_model(Action)
    assert stale_customization.field_name == 'identifier'


def test_a_customization_of_a_vanished_model_can_be_deleted(admin_client, stale_customization):
    response = admin_client.post(reverse(DELETE_URL_NAME, args=[stale_customization.pk]))
    assert response.status_code == 302
    assert not BuiltInFieldCustomization.objects.filter(pk=stale_customization.pk).exists()


def test_the_model_column_and_the_filter_agree(admin_client, plan):
    """
    The listing and the filter must not show two spellings of the same content type.

    `ContentType.__str__` renders "Actions | action", which would sit next to the filter's "Action".
    """
    customization = BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(Action),
        field_name='identifier',
    )
    response = admin_client.get(reverse(LIST_URL_NAME))

    assert customization.content_type_label == 'Action'
    assert str(customization.content_type) not in response.content.decode()
    filter_labels = {str(label) for _value, label in response.context['filters'].filters['content_type'].field.choices}
    assert customization.content_type_label in filter_labels


def test_the_model_column_stays_sortable(admin_client, plan):
    """Rendering the column through a property must not cost the sorting the raw column had."""
    BuiltInFieldCustomizationFactory.create(plan=plan, field_name='identifier')
    assert 'ordering=content_type' in admin_client.get(reverse(LIST_URL_NAME)).content.decode()


def test_the_model_column_of_a_vanished_model_falls_back(stale_customization):
    assert stale_customization.content_type_label == 'gone_app | gonemodel'


def test_field_choice_labels_are_consistently_capitalized():
    """
    Most `verbose_name`s are lower case, but a handful are capitalized in the model itself.

    The labels are capitalized on the way out so the widget does not mix the two spellings.
    """
    labels = [label for _group, choices in get_field_choices() for _value, label in choices]
    assert labels
    assert [label for label in labels if not label[:1].isupper()] == []
def test_the_listing_links_each_row_to_its_edit_view(admin_client, plan):
    """
    Wagtail builds the linked title column only from a `list_display` entry given as a name.

    A `Column` instance in the first position is used verbatim, which leaves the listing with no way
    to open a row and drops the row's buttons along with the link.
    """
    customization = BuiltInFieldCustomizationFactory.create(plan=plan, field_name='identifier')
    html = admin_client.get(reverse(LIST_URL_NAME)).content.decode()
    assert f'href="{reverse(EDIT_URL_NAME, args=[customization.pk])}"' in html
    assert f'href="{reverse(DELETE_URL_NAME, args=[customization.pk])}"' in html
