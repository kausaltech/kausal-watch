from django.db import migrations
from django.utils import translation


def check_accessibility_statement_exists(apps, schema_editor):
    AccessibilityStatementPage = apps.get_model('pages', 'AccessibilityStatementPage')
    Locale = apps.get_model('wagtailcore', 'Locale')
    SiteGeneralContent = apps.get_model('content', 'SiteGeneralContent')
    for content in SiteGeneralContent.objects.all():
        plan = content.plan
        locale = Locale.objects.get(language_code=plan.primary_language)
        with translation.override(plan.primary_language):
            # This is ridiculously crude
            need_check = content.accessibility_contact_email or content.accessibility_responsible_body
            if need_check and not AccessibilityStatementPage.objects.filter(
                locale=locale,
                body__contains='contact_information',
            ).exists():
                raise Exception(f"Plan {plan.identifier} has accessibility contact information in its general_content "
                                "but no accessibility statement page with contact_information block. This migration "
                                "will be aborted as otherwise the accessibility contact information would be lost. Run "
                                "the plan's create_default_pages method to create an accessibility statement with the "
                                "information. Make sure you run it on a version of the code that adds the appropriate "
                                "contact_information block to it.")


class Migration(migrations.Migration):
    dependencies = [
        ('content', '0004_add_action_term_field'),
        ('pages', '0008_privacy_policy_and_accessibility_statement'),
    ]

    operations = [
        migrations.RunPython(check_accessibility_statement_exists),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='accessibility_contact_email',
        ),
        migrations.RemoveField(
            model_name='sitegeneralcontent',
            name='accessibility_responsible_body',
        ),
    ]
