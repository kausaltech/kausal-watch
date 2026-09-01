from django.db import migrations

MODELS = ['datasource', 'organization', 'admin_users', 'organizationclass', 'organization_regular_users']


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0006_alter_user_deactivated_by'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[f'DROP TABLE IF EXISTS django_orghierarchy_{model} CASCADE;' for model in MODELS]
        ),
    ]
