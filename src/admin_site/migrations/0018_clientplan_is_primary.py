from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_site", "0017_builtinfieldcustomization_latest_revision"),
    ]

    operations = [
        migrations.AddField(
            model_name="clientplan",
            name="is_primary",
            field=models.BooleanField(
                default=False,
                help_text="The tenant that owns this plan. Used to scope public user identities and staff notifications for pledge sign-ups.",
                verbose_name="primary client",
            ),
        ),
        migrations.AddConstraint(
            model_name="clientplan",
            constraint=models.UniqueConstraint(
                fields=("plan",),
                condition=models.Q(("is_primary", True)),
                name="unique_primary_client_per_plan",
            ),
        ),
    ]
