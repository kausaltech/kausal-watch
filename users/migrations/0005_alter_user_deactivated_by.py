# Generated by Django 3.2.13 on 2023-01-20 10:48

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_add_user_deactivation_metadata'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='deactivated_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
    ]