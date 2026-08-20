from __future__ import annotations

from django.db import migrations


def backfill_public_user_client(apps, schema_editor):
    PublicUser = apps.get_model('actions', 'PublicUser')

    candidates = PublicUser.objects.filter(client__isnull=True, email__isnull=True)
    for user in candidates.iterator():
        client_ids = set(
            user.commitments.filter(pledge__plan__clients__is_primary=True).values_list(
                'pledge__plan__clients__client_id', flat=True,
            )
        )
        if len(client_ids) == 1:
            user.client_id = client_ids.pop()
            user.save(update_fields=['client'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0186_public_user_client_scope'),
    ]

    operations = [
        migrations.RunPython(backfill_public_user_client, noop_reverse),
    ]
