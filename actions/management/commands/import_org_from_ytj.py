import re
import requests
from django.core.management.base import BaseCommand

from actions.models import Plan
from orgs.models import Organization, OrganizationClass, OrganizationIdentifier, Namespace


class Command(BaseCommand):
    help = 'Import an organisation from YTJ'

    def import_organisation(self, name_or_id):
        namespace = Namespace.objects.get(identifier='ytj')

        if not name_or_id[0].isnumeric():
            resp = requests.get('https://avoindata.prh.fi/bis/v1?name=%s' % name_or_id)
            resp.raise_for_status()
            res = resp.json()['results']
            if len(res) == 0:
                print('No matches for: %s' % name_or_id)
                return
            elif len(res) > 1:
                print('Multiple matches for: %s' % name_or_id)
                for org in res:
                    print('\t%s: %s' % (res['businessId'], res['name']))
                return
            else:
                data = res[0]
        else:
            resp = requests.get('https://avoindata.prh.fi/bis/v1/%s' % name_or_id)
            resp.raise_for_status()
            res = resp.json()['results']
            if len(res) == 0:
                print('No matches for: %s' % name_or_id)
                return
            assert len(res) == 1
            data = res[0]

        form = data['companyForm']
        assert form == 'OY'

        org_identifier = (OrganizationIdentifier.objects.filter(namespace=namespace, identifier=data['businessId'])
                          .first())
        if org_identifier is None:
            print('Creating %s (%s)' % (data['name'], data['businessId']))
            org = Organization()
        else:
            org = org_identifier.organization

        org.name = data['name']
        org.classification = OrganizationClass.objects.get(name='Osakeyhtiö')
        if not org.abbreviation:
            abbr = re.sub(' [oO][yY]', '', org.name)
            org.abbreviation = abbr
        org.save()

        if org_identifier is None:
            org_identifier.objects.create(namespace=namespace, identifier=data['businessId'], organization=org)

        print('Imported %s (%s)' % (org.name, org.id))
        if self.plan:
            self.plan.related_organizations_new.add(org)

    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument('name_or_id', nargs='+', type=str)

        # Named (optional) arguments
        parser.add_argument(
            '--plan',
            help='Add imported organisation to plan',
        )

    def handle(self, *args, **options):
        if options['plan']:
            self.plan = Plan.objects.get(identifier=options['plan'])
        else:
            self.plan = None

        for name_or_id in options['name_or_id']:
            print(name_or_id)
            self.import_organisation(name_or_id)
