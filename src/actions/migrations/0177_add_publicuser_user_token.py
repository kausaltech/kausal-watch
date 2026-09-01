from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("actions", "0176_rename_pledgecommitment_pledge_user_public_user"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicuser",
            name="user_token",
            field=models.CharField(
                blank=True,
                editable=False,
                help_text="Opaque secret used as a bearer credential after the user signs up.",
                max_length=64,
                null=True,
                unique=True,
                verbose_name="user token",
            ),
        ),
    ]
