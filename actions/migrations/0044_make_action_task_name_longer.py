# Generated by Django 2.2.11 on 2020-04-22 19:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0043_make_action_responsible_party_org_unique'),
    ]

    operations = [
        migrations.AlterField(
            model_name='actiontask',
            name='name',
            field=models.CharField(max_length=250, verbose_name='name'),
        ),
    ]