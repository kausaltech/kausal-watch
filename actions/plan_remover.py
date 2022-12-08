from django.db import transaction
from django.utils import translation

from wagtail.core.models import Page
from wagtail.core.models.i18n import Locale

from people.models import Person


def persons_not_related_to_other_plans(plan):
    persons_to_delete = []
    persons_to_leave = []
    for person in Person.objects.exclude(user__is_superuser=True).distinct():
        adminable_plans = person.user.get_adminable_plans()
        if adminable_plans.count() == 1 and plan in adminable_plans:
            persons_to_delete.append(person)
        else:
            persons_to_leave.append(person)
    return (persons_to_delete, persons_to_leave)


@transaction.atomic
def remove_people(persons):
    for person in persons:
        person.user.delete()
        person.delete()


@transaction.atomic
def remove_plan(plan):
    plan.notification_base_template.content_blocks.all().delete()

    plan.primary_action_classification = None
    plan.secondary_action_classification = None
    plan.save()

    # Wagtail site and pages
    for language_code in (plan.primary_language, *plan.other_languages):
        with translation.override(language_code):
            try:
                root_page = plan.get_translated_root_page()
                root_page.get_descendants().delete()
                root_page.delete()
            except (Locale.DoesNotExist, Page.DoesNotExist):
                pass

    plan.site.delete()

    for category_type in plan.category_types.all():
        category_type.categories.all().delete()
        category_type.delete()

    plan.actions.all().delete()

    admin_group = plan.admin_group
    contact_person_group = plan.contact_person_group
    plan.delete()
    admin_group.delete()
    contact_person_group.delete()
