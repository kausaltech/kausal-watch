#!/usr/bin/env python
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aplans.settings')
django.setup()

from django_orghierarchy import models as doh  # noqa
from orgs.models import Namespace, Organization, OrganizationClass, OrganizationIdentifier  # noqa


def migrate_data_sources():
    for data_source in doh.DataSource.objects.all():
        defaults = {
            'name': data_source.name,
            'user_editable': data_source.user_editable,
        }
        Namespace.objects.update_or_create(
            identifier=data_source.id,
            defaults=defaults,
        )


def migrate_organization_classes():
    for doh_org_class in doh.OrganizationClass.objects.all():
        defaults = {
            'name': doh_org_class.name,
            'created_time': doh_org_class.created_time,
            'last_modified_time': doh_org_class.last_modified_time,
        }
        OrganizationClass.objects.update_or_create(
            identifier=doh_org_class.id,
            defaults=defaults,
        )


def migrate_organization(doh_org):
    assert not OrganizationIdentifier.objects.filter(
        identifier=doh_org.id,
        namespace=Namespace.objects.get(identifier=doh_org.data_source.id)
    ).exists()

    org = Organization()
    org.classification = OrganizationClass.objects.get(identifier=doh_org.classification_id)
    org.name = doh_org.name
    org.abbreviation = doh_org.abbreviation or ''
    # TODO: distinct_name
    org.founding_date = doh_org.founding_date
    org.dissolution_date = doh_org.dissolution_date
    org.created_time = doh_org.created_time
    org.created_by = doh_org.created_by
    org.last_modified_time = doh_org.last_modified_time
    org.last_modified_by = doh_org.last_modified_by

    if doh_org.parent is None:
        Organization.add_root(instance=org)
    else:
        parent_namespace = Namespace.objects.get(identifier=doh_org.parent.data_source.id)
        parent_identifier = OrganizationIdentifier.objects.get(namespace=parent_namespace, identifier=doh_org.parent.id)
        parent = parent_identifier.organization
        parent.add_child(instance=org)
    return org


def migrate_organization_identifier(doh_org, org):
    namespace = Namespace.objects.get(identifier=doh_org.data_source.id)
    defaults = {
        'organization': org,
    }
    OrganizationIdentifier.objects.update_or_create(
        identifier=doh_org.id,
        namespace=namespace,
        defaults=defaults,
    )


def migrate_organizations():
    for doh_org in doh.Organization.objects.all():
        try:
            org = migrate_organization(doh_org)
            migrate_organization_identifier(doh_org, org)
        except OrganizationClass.DoesNotExist:
            print(f"Skipping organization {doh_org.id} since it has no classification")
            continue


if __name__ == '__main__':
    OrganizationIdentifier.objects.all().delete()
    Organization.objects.all().delete()
    OrganizationClass.objects.all().delete()
    Namespace.objects.all().delete()
    migrate_data_sources()
    migrate_organization_classes()
    migrate_organizations()
