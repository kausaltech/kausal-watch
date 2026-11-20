"""
Switch on contact person roles in plans that rely on them.

Plans without contact person roles used to show the "Editor" and "Moderator" sections anyway, but now they don't, and
every contact person acts as a moderator there (see `ActionContactPerson.moderators_q()`). The roles still matter in
some plans, so we switch them on there:

- A plan with editors, live or in a draft, and a moderation workflow: only moderators may approve, so without roles, the editors could.
- A plan with editors and fields restricted to moderators: without roles, the editors could access them.
- A plan that hides moderators on the public site: without roles, it would show every contact person.
"""

from __future__ import annotations

from django.db import migrations
from django.db.models import Q


def enable_roles_where_in_use(apps, schema_editor):
    PlanFeatures = apps.get_model('actions', 'PlanFeatures')
    Action = apps.get_model('actions', 'Action')
    ActionContactPerson = apps.get_model('actions', 'ActionContactPerson')
    AttributeType = apps.get_model('actions', 'AttributeType')
    BuiltInFieldCustomization = apps.get_model('admin_site', 'BuiltInFieldCustomization')

    plans_with_editors = ActionContactPerson.objects.filter(role='editor').values('action__plan')
    # Moderation checks the draft, so editors who exist only there count too
    plans_with_draft_editors = Action.objects.filter(
        has_unpublished_changes=True, latest_revision__content__contact_persons__contains=[{'role': 'editor'}]
    ).values('plan')
    restricted_to_moderators = Q(instances_editable_by='moderators') | Q(instances_visible_for='moderators')
    # Customizations of models other than actions treat moderators as plan admins, but switching roles on for them too
    # does no harm.
    plans_with_moderator_fields = BuiltInFieldCustomization.objects.filter(restricted_to_moderators).values('plan')
    plans_with_moderator_attributes = AttributeType.objects.filter(
        restricted_to_moderators, scope_content_type__app_label='actions', scope_content_type__model='plan'
    ).values('scope_id')
    role_matters = (
        Q(moderation_workflow__isnull=False)
        | Q(plan__in=plans_with_moderator_fields)
        | Q(plan__in=plans_with_moderator_attributes)
    )
    relies_on_roles = Q(contact_persons_hide_moderators=True) | (
        (Q(plan__in=plans_with_editors) | Q(plan__in=plans_with_draft_editors)) & role_matters
    )
    PlanFeatures.objects.filter(relies_on_roles, has_action_contact_person_roles=False).update(
        has_action_contact_person_roles=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0207_pledge_feedback_enabled_and_impact_text_length'),
        ('admin_site', '0020_backfill_primary_clientplan'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(enable_roles_where_in_use, migrations.RunPython.noop),
    ]
