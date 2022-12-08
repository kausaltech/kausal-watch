from django.core.management.base import BaseCommand
import sys

from actions.models.plan import Plan
from actions.plan_remover import (
    remove_plan as do_remove_plan,
    remove_people as do_remove_people,
    persons_not_related_to_other_plans
)


def _ask_if_continue(question, default=None, answer=None):
    result = input("%s " % question)
    if not result and default is not None:
        return default
    if answer is None:
        while len(result) < 1 or result[0].lower() not in "yn":
            result = input("Please answer yes or no: ")
        return result[0].lower() == "y"
    return result == answer


def exit_if_abort(question, answer=None):
    if not _ask_if_continue(question, answer=answer):
        print('Removal cancelled')
        sys.exit(1)


def remove_people(persons, plan):
    exit_if_abort(
        f'About to completely remove {len(persons)} persons and users which are only connected to "{plan}".'
        ' Confirm with [y]es.',
    )
    do_remove_people(persons)


class Command(BaseCommand):
    help = 'Completely and interactively removes a plan and all objects only related to that plan'

    def add_arguments(self, parser):
        parser.add_argument('--plan', type=str, help='Identifier of the action plan')
        parser.add_argument(
            '--delete-persons-and-users',
            action='store_true',
            help='Whether to also delete the corresponding persons and their users'
        )

    def handle(self, plan, delete_persons_and_users, *args, **options):
        try:
            plan = Plan.objects.get(identifier=plan)
        except Plan.DoesNotExist:
            print(f'Plan {plan} does not exist')
            sys.exit(2)

        exit_if_abort(
            f'About to completely remove plan "{plan}". '
            'Confirm by typing the exact identifier of the plan:',
            plan.identifier
        )
        if delete_persons_and_users:
            print('Calculating related persons.')
            persons_to_delete, _ = persons_not_related_to_other_plans(plan)
        do_remove_plan(plan)
        if delete_persons_and_users:
            remove_people(persons_to_delete, plan)
