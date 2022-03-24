# Generated by Django 3.2.12 on 2022-02-24 08:52

from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


def migrate_general_plan_admins(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    GeneralPlanAdmin = apps.get_model('actions', 'GeneralPlanAdmin')
    for plan in Plan.objects.all():
        for i, person in enumerate(plan.general_admins.all()):
            GeneralPlanAdmin.objects.create(plan=plan, person=person, order=i)


def migrate_general_plan_admins_reverse(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    for plan in Plan.objects.all():
        for row in plan.general_admins_ordered.all():
            Plan.general_admins.through.objects.create(person=row.person, plan=row.plan)


class Migration(migrations.Migration):

    dependencies = [
        ('people', '0002_person_user'),
        ('actions', '0012_plan_general_admin_persons'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeneralPlanAdmin',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='general_admin_plans_ordered', to='people.person', verbose_name='person')),
                ('plan', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='general_admins_ordered', to='actions.plan', verbose_name='plan')),
            ],
            options={
                'verbose_name': 'general plan admin',
                'verbose_name_plural': 'general plan admins',
                'ordering': ['plan', 'order'],
                'unique_together': {('plan', 'person')},
                'index_together': {('plan', 'order')},
            },
        ),
        migrations.RunPython(migrate_general_plan_admins, migrate_general_plan_admins_reverse),
        migrations.RemoveField(
            model_name='plan',
            name='general_admins',
        ),
        migrations.AddField(
            model_name='plan',
            name='general_admins',
            field=models.ManyToManyField(blank=True, help_text='Persons that can modify everything related to the action plan', related_name='general_admin_plans', through='actions.GeneralPlanAdmin', to='people.Person', verbose_name='general administrators'),
        ),
    ]