from django.db import migrations

from aplans.utils import get_default_country


def set_default_country(apps, schema_editor):
    Plan = apps.get_model("actions", "Plan")
    Plan.objects.filter(country="").update(country=get_default_country())


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("actions", "0178_attributetypechoiceoption_is_active"),
    ]

    operations = [
        migrations.RunPython(set_default_country, noop),
    ]
