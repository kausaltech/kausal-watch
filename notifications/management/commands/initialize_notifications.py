from random import randrange
import re

from django.utils import translation
from django.utils.translation import pgettext
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from actions.models import Plan
from notifications.models import BaseTemplate, NotificationType, AutomaticNotificationTemplate, ContentBlock


ALPHANUM = 'abcdefghijklmnopqrstuvwxyz0123456789'


def generate_draftail_block_key():
    return ''.join((ALPHANUM[randrange(0, len(ALPHANUM))] for _ in range(0, 5)))


def split_into_draftail_paragraphs(s):
    return "\n".join((f'<p data-block-key="{generate_draftail_block_key()}">{x.strip()}</p>'
                      for x in re.split(r'\n\n+', s.strip())))


def initialize_notification_templates(
    plan_identifier=None
):
    plan = Plan.objects.get(identifier=plan_identifier)
    locale = plan.primary_language
    translation.activate(locale)
    base_template_defaults = {
        'from_name': plan.name,
        'from_address': settings.DEFAULT_FROM_EMAIL,
        'reply_to': None,
        'brand_dark_color': None,
        'logo_id': None,
        'font_family': None,
        'font_css_url': None
    }
    default_intro_texts_for_notification_type = {
        'action_not_updated': pgettext(
            'action_not_updated',
            "This is an automatic reminder about "
            "updating the action details in the action plan.  You can "
            "see on the action plan watch site what has already been done "
            "to further the actions and what has been planned for the "
            "future.  It's already six months since you last updated an "
            "action. Please go and update the action with the latest "
            "information. You can add an upcoming task to the action at "
            "the same time."),
        'not_enough_tasks': pgettext(
            'not_enough_tasks',
            "This is an automatic reminder about "
            "updating the action details in the action plan.  You can "
            "see on the action plan watch site what has already been "
            "done to further the actions and what has been planned for "
            "the future.  This means that it would be preferrable for "
            "each action to have at least one upcoming task within the "
            "next year. Please go and add tasks for the action which "
            "show what the next planned steps for the action are."),
        'task_due_soon': pgettext(
            'task_due_soon',
            "This is an automatic reminder about "
            "updating the task information of your action in the action "
            "plan.  There is an action in the action plan with a "
            "deadline approaching. Please remember to mark the task as "
            "done as soon as it has been completed. After the deadline "
            "has gone, the action will be marked as late. You can edit "
            "the task details from the link below."),
        'task_late': pgettext(
            'task_late',
            "This is an automatic reminder about updating "
            "the task information of your action in the action plan. "
            "There is an action whose deadline has passed. The action "
            "is shown to be late until you mark it as done and fill in "
            "some details."),
        'updated_indicator_values_due_soon': pgettext(
            'updated_indicator_values_due_soon',
            "This is an automatic "
            "reminder about updating indicator details in the action "
            "plan.  The deadline for updating the indicator values is "
            "approaching. Please go and update the indicator with the "
            "latest values."),
        'updated_indicator_values_late': pgettext(
            'updated_indicator_values_late',
            "This is an automatic "
            "reminder about updating indicator details in the action "
            "plan.  The deadline for updating the indicator values has "
            "passed. Please go and update the indicator with the latest "
            "values."),
        'user_feedback_received': pgettext(
            'user_feedback_received',
            "A user has submitted feedback."),
    }

    base_template, created = BaseTemplate.objects.get_or_create(plan=plan, defaults=base_template_defaults)
    for notification_type in NotificationType:
        defaults = {
            'subject': notification_type.verbose_name,
        }
        template, created = AutomaticNotificationTemplate.objects.get_or_create(
            base=base_template, type=notification_type.identifier, defaults=defaults)
        ContentBlock.objects.get_or_create(
            template=template, identifier='intro', base=base_template,
            defaults={'content': split_into_draftail_paragraphs(
                default_intro_texts_for_notification_type.get(notification_type.identifier))})

    default_shared_texts = {
        'motivation': pgettext(
            'motivation',
            "Thank you for keeping the action plan updated. "
            "Up-to-date information about the actions is essential "
            "for us to achieve our goals."),
        'outro': pgettext(
            'outro',
            "If you are having difficulties using the action "
            "plan watch platform, please send an email to the "
            "administrators of the action plan.\n\n"
            "Thank you for taking part in implementing the action plan!\n\n"
            "Kind regards,\nthe action plan administrators"),
    }

    for block_type in ['motivation', 'outro']:
        ContentBlock.objects.get_or_create(
            template=None, identifier=block_type, base=base_template,
            defaults={'content': split_into_draftail_paragraphs(default_shared_texts.get(block_type))}
        )


class Command(BaseCommand):
    help = 'Initializes the email notification templates to a good value'

    def add_arguments(self, parser):
        parser.add_argument('--plan', type=str, help='Identifier of the action plan')

    def handle(self, *args, **options):
        if not options['plan']:
            raise CommandError('No plan supplied')

        initialize_notification_templates(
            plan_identifier=options['plan'],
        )
