from django.db import migrations


def force_light(apps, schema_editor):
    UserProfile = apps.get_model('wagtailusers', 'UserProfile')
    UserProfile.objects.all().update(theme='light')


def force_system(apps, schema_editor):
    UserProfile = apps.get_model('wagtailusers', 'UserProfile')
    UserProfile.objects.all().update(theme='system')


class Migration(migrations.Migration):

    dependencies = [
        ('admin_site', '0005_remove_client_fields'),
        ('wagtailusers', '0012_userprofile_theme'),
    ]

    operations = [
        migrations.RunPython(force_light, reverse_code=force_system),
    ]
