# Generated by Django 2.2.4 on 2019-10-12 09:43

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('people', '0005_add_person_title'),
        ('actions', '0030_rename_contact_persons'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActionStatusUpdate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='title')),
                ('date', models.DateField(default=datetime.date.today, verbose_name='date')),
                ('content', models.TextField(verbose_name='content')),
                ('created_at', models.DateField(auto_now_add=True, verbose_name='created at')),
                ('modified_at', models.DateField(auto_now=True, verbose_name='created at')),
                ('action', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_updates', to='actions.Action', verbose_name='action')),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='status_updates', to='people.Person', verbose_name='author')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='created by')),
            ],
            options={
                'verbose_name': 'action status update',
                'verbose_name_plural': 'action status updates',
            },
        ),
    ]
