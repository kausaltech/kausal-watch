import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("actions", "0175_rename_pledgeuser_publicuser_and_more"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="pledgecommitment",
            unique_together=set(),
        ),
        migrations.RenameField(
            model_name="pledgecommitment",
            old_name="pledge_user",
            new_name="public_user",
        ),
        migrations.AlterField(
            model_name="pledgecommitment",
            name="public_user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="commitments",
                to="actions.publicuser",
                verbose_name="public user",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="pledgecommitment",
            unique_together={("pledge", "public_user")},
        ),
    ]
