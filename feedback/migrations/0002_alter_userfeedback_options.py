# Generated by Django 3.2.13 on 2022-08-08 17:42

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='userfeedback',
            options={'verbose_name': 'user feedback', 'verbose_name_plural': 'user feedbacks'},
        ),
    ]