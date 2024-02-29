from django.core.management.base import BaseCommand, CommandError, CommandParser
from actions.models import Plan
from people.models import Person
from users.models import User
from orgs.models import Organization


class Command(BaseCommand):
    help = "Create a test user"

    def add_arguments(self, parser: CommandParser):
        parser.add_argument('email', type=str)
        parser.add_argument('--admin-plan', type=str, action='append', help='User is admin for plan')
        parser.add_argument('-r', '--remove', action='store_true', help='Remove the test user')
        parser.add_argument('-o', '--org', type=str, help='Add user in this organization')
        parser.add_argument('-p', '--password', type=str, help='Set the password for the user')

    def handle(self, *args, **options):
        email = options['email'].strip().lower()
        existing = Person.objects.filter(email__iexact=email).first()
        if options['remove']:
            if not existing:
                self.stderr.write(
                    self.style.ERROR('Person with that email does not exist')
                )
                exit(1)
            out = existing.delete()
            self.stdout.write(
                self.style.SUCCESS('User deleted')
            )
            exit(0)

        if existing:
            self.stderr.write(
                self.style.ERROR('User with email %s already exists' % email)
            )
            exit(1)

        admin_plans = []
        for plan_id in options['admin_plan']:
            admin_plans.append(Plan.objects.get(identifier=plan_id))

        if options['org']:
            org_name = options['org']
            orgs = Organization.objects.filter(name__iexact=org_name)
            if not orgs:
                orgs = Organization.objects.filter(name__icontains=org_name)
            if orgs.count() != 1:
                self.stderr.write(
                    self.style.ERROR('Invalid number of organizations matched "%s": %s' % (org_name, ', '.join([o.name for o in orgs])))
                )
                exit(1)
            org = orgs[0]
        else:
            if not admin_plans:
                self.stderr.write(
                    self.style.ERROR('Unable to determine organization for user')
                )
                exit(1)
            org = admin_plans[0].organization

        p = Person.objects.create(email=email, first_name='First', last_name='Last', organization=org)
        p.create_corresponding_user()
        if admin_plans:
            p.general_admin_plans.add(*admin_plans)

        if options['password']:
            u = p.user
            u.set_password(options['password'])
            u.save()

        self.stdout.write(
            self.style.SUCCESS('Created test user with email "%s" and organization "%s"' % (p.email, org.name))
        )
