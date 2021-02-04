import sys
import requests
from django_orghierarchy.models import Organization, DataSource, OrganizationClass
from django.core.management.base import BaseCommand
from actions.models import Plan


class Command(BaseCommand):
    help = 'Import an organisation from YTJ'

    def import_organisation(self, name_or_id):
        ds = DataSource.objects.get(id='ytj')

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

        org = Organization.objects.filter(data_source=ds, origin_id=data['businessId']).first()
        if org is None:
            print('Creating %s (%s)' % (data['name'], data['businessId']))
            org = Organization(data_source=ds, origin_id=data['businessId'])
        org.name = data['name']
        org.classification = OrganizationClass.objects.get(name='Osakeyhtiö')
        org.save()
        print('Imported %s (%s)' % (org.name, org.id))
        if self.plan:
            self.plan.related_organizations.add(org)

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
