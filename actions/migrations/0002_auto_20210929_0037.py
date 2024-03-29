# Generated by Django 3.1.5 on 2021-09-28 21:37

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('actions', '0001_initial'),
        ('images', '0002_auto_20210929_0037'),
        ('wagtailcore', '0060_fix_workflow_unique_constraint'),
        ('people', '0002_person_user'),
        ('orgs', '0002_auto_20210929_0037'),
        ('indicators', '0002_auto_20210929_0037'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='plan',
            name='general_admins',
            field=models.ManyToManyField(blank=True, help_text='Users that can modify everything related to the action plan', related_name='general_admin_plans', to=settings.AUTH_USER_MODEL, verbose_name='general administrators'),
        ),
        migrations.AddField(
            model_name='plan',
            name='image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.aplansimage'),
        ),
        migrations.AddField(
            model_name='plan',
            name='organization',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='plans', to='orgs.organization', verbose_name='main organization for the plan'),
        ),
        migrations.AddField(
            model_name='plan',
            name='related_organizations',
            field=models.ManyToManyField(blank=True, related_name='related_plans', to='orgs.Organization'),
        ),
        migrations.AddField(
            model_name='plan',
            name='root_collection',
            field=models.OneToOneField(editable=False, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='plan', to='wagtailcore.collection'),
        ),
        migrations.AddField(
            model_name='plan',
            name='site',
            field=models.OneToOneField(editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='plan', to='wagtailcore.site'),
        ),
        migrations.AddField(
            model_name='monitoringqualitypoint',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='monitoring_quality_points', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='impactgroupaction',
            name='action',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='impact_groups', to='actions.action', verbose_name='action'),
        ),
        migrations.AddField(
            model_name='impactgroupaction',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='actions.impactgroup', verbose_name='name'),
        ),
        migrations.AddField(
            model_name='impactgroupaction',
            name='impact',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='actions.actionimpact', verbose_name='impact'),
        ),
        migrations.AddField(
            model_name='impactgroup',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='actions.impactgroup', verbose_name='parent'),
        ),
        migrations.AddField(
            model_name='impactgroup',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='impact_groups', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='categorytypemetadatachoice',
            name='metadata',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='choices', to='actions.categorytypemetadata'),
        ),
        migrations.AddField(
            model_name='categorytypemetadata',
            name='type',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='metadata', to='actions.categorytype'),
        ),
        migrations.AddField(
            model_name='categorytype',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='category_types', to='actions.plan'),
        ),
        migrations.AddField(
            model_name='categorymetadatarichtext',
            name='category',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='metadata_richtexts', to='actions.category'),
        ),
        migrations.AddField(
            model_name='categorymetadatarichtext',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='category_richtexts', to='actions.categorytypemetadata'),
        ),
        migrations.AddField(
            model_name='categorymetadatanumericvalue',
            name='category',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='metadata_numeric_values', to='actions.category'),
        ),
        migrations.AddField(
            model_name='categorymetadatanumericvalue',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='category_numeric_values', to='actions.categorytypemetadata'),
        ),
        migrations.AddField(
            model_name='categorymetadatachoice',
            name='category',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='metadata_choices', to='actions.category'),
        ),
        migrations.AddField(
            model_name='categorymetadatachoice',
            name='choice',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='categories', to='actions.categorytypemetadatachoice'),
        ),
        migrations.AddField(
            model_name='categorymetadatachoice',
            name='metadata',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='category_choices', to='actions.categorytypemetadata'),
        ),
        migrations.AddField(
            model_name='categorylevel',
            name='type',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='levels', to='actions.categorytype', verbose_name='type'),
        ),
        migrations.AddField(
            model_name='category',
            name='image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.aplansimage'),
        ),
        migrations.AddField(
            model_name='category',
            name='parent',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='children', to='actions.category', verbose_name='parent category'),
        ),
        migrations.AddField(
            model_name='category',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='categories', to='actions.categorytype', verbose_name='type'),
        ),
        migrations.AddField(
            model_name='actiontask',
            name='action',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to='actions.action', verbose_name='action'),
        ),
        migrations.AddField(
            model_name='actiontask',
            name='completed_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='completed by'),
        ),
        migrations.AddField(
            model_name='actionstatusupdate',
            name='action',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_updates', to='actions.action', verbose_name='action'),
        ),
        migrations.AddField(
            model_name='actionstatusupdate',
            name='author',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='status_updates', to='people.person', verbose_name='author'),
        ),
        migrations.AddField(
            model_name='actionstatusupdate',
            name='created_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name='created by'),
        ),
        migrations.AddField(
            model_name='actionstatus',
            name='plan',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_statuses', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='actionschedule',
            name='plan',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_schedules', to='actions.plan'),
        ),
        migrations.AddField(
            model_name='actionresponsibleparty',
            name='action',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='responsible_parties', to='actions.action', verbose_name='action'),
        ),
        migrations.AddField(
            model_name='actionresponsibleparty',
            name='organization',
            field=models.ForeignKey(limit_choices_to=models.Q(dissolution_date=None), on_delete=django.db.models.deletion.CASCADE, related_name='responsible_actions', to='orgs.organization', verbose_name='organization'),
        ),
        migrations.AddField(
            model_name='actionlink',
            name='action',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='links', to='actions.action', verbose_name='action'),
        ),
        migrations.AddField(
            model_name='actionimplementationphase',
            name='plan',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_implementation_phases', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='actionimpact',
            name='plan',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_impacts', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='actiondecisionlevel',
            name='plan',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='action_decision_levels', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='actioncontactperson',
            name='action',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='contact_persons', to='actions.action', verbose_name='action'),
        ),
        migrations.AddField(
            model_name='actioncontactperson',
            name='person',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='people.person', verbose_name='person'),
        ),
        migrations.AddField(
            model_name='action',
            name='categories',
            field=models.ManyToManyField(blank=True, to='actions.Category', verbose_name='categories'),
        ),
        migrations.AddField(
            model_name='action',
            name='contact_persons_unordered',
            field=models.ManyToManyField(blank=True, related_name='contact_for_actions', through='actions.ActionContactPerson', to='people.Person', verbose_name='contact persons'),
        ),
        migrations.AddField(
            model_name='action',
            name='decision_level',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='actions', to='actions.actiondecisionlevel', verbose_name='decision-making level'),
        ),
        migrations.AddField(
            model_name='action',
            name='image',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='images.aplansimage'),
        ),
        migrations.AddField(
            model_name='action',
            name='impact',
            field=models.ForeignKey(blank=True, help_text='The impact of this action', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='actions', to='actions.actionimpact', verbose_name='impact'),
        ),
        migrations.AddField(
            model_name='action',
            name='implementation_phase',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='actions.actionimplementationphase', verbose_name='implementation phase'),
        ),
        migrations.AddField(
            model_name='action',
            name='indicators',
            field=models.ManyToManyField(blank=True, related_name='actions', through='indicators.ActionIndicator', to='indicators.Indicator', verbose_name='indicators'),
        ),
        migrations.AddField(
            model_name='action',
            name='merged_with',
            field=models.ForeignKey(blank=True, help_text='Set if this action is merged with another action', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='merged_actions', to='actions.action', verbose_name='merged with action'),
        ),
        migrations.AddField(
            model_name='action',
            name='monitoring_quality_points',
            field=models.ManyToManyField(blank=True, editable=False, related_name='actions', to='actions.MonitoringQualityPoint'),
        ),
        migrations.AddField(
            model_name='action',
            name='plan',
            field=modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='actions.plan', verbose_name='plan'),
        ),
        migrations.AddField(
            model_name='action',
            name='responsible_organizations',
            field=models.ManyToManyField(blank=True, related_name='responsible_for_actions', through='actions.ActionResponsibleParty', to='orgs.Organization', verbose_name='responsible organizations'),
        ),
        migrations.AddField(
            model_name='action',
            name='schedule',
            field=models.ManyToManyField(blank=True, to='actions.ActionSchedule', verbose_name='schedule'),
        ),
        migrations.AddField(
            model_name='action',
            name='status',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='actions.actionstatus', verbose_name='status'),
        ),
        migrations.AlterUniqueTogether(
            name='scenario',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='monitoringqualitypoint',
            unique_together={('plan', 'order')},
        ),
        migrations.AlterUniqueTogether(
            name='impactgroupaction',
            unique_together={('group', 'action')},
        ),
        migrations.AlterUniqueTogether(
            name='impactgroup',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='categorytypemetadatachoice',
            unique_together={('metadata', 'order'), ('metadata', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='categorytypemetadata',
            unique_together={('type', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='categorytype',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='categorymetadatarichtext',
            unique_together={('category', 'metadata')},
        ),
        migrations.AlterUniqueTogether(
            name='categorymetadatanumericvalue',
            unique_together={('category', 'metadata')},
        ),
        migrations.AlterUniqueTogether(
            name='categorymetadatachoice',
            unique_together={('category', 'metadata')},
        ),
        migrations.AlterUniqueTogether(
            name='categorylevel',
            unique_together={('type', 'order')},
        ),
        migrations.AlterUniqueTogether(
            name='category',
            unique_together={('type', 'external_identifier'), ('type', 'identifier')},
        ),
        migrations.AddConstraint(
            model_name='actiontask',
            constraint=models.CheckConstraint(check=models.Q(models.Q(_negated=True, state='completed'), ('completed_at__isnull', False), _connector='OR'), name='actions_actiontask_completed_at_if_completed'),
        ),
        migrations.AddConstraint(
            model_name='actiontask',
            constraint=models.CheckConstraint(check=models.Q(('completed_at__isnull', True), ('state', 'completed'), _connector='OR'), name='actions_actiontask_completed_if_completed_at'),
        ),
        migrations.AlterUniqueTogether(
            name='actionstatus',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='actionresponsibleparty',
            unique_together={('action', 'organization')},
        ),
        migrations.AlterIndexTogether(
            name='actionresponsibleparty',
            index_together={('action', 'order')},
        ),
        migrations.AlterIndexTogether(
            name='actionlink',
            index_together={('action', 'order')},
        ),
        migrations.AlterUniqueTogether(
            name='actionimplementationphase',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='actionimpact',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='actiondecisionlevel',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterUniqueTogether(
            name='actioncontactperson',
            unique_together={('action', 'person')},
        ),
        migrations.AlterIndexTogether(
            name='actioncontactperson',
            index_together={('action', 'order')},
        ),
        migrations.AlterUniqueTogether(
            name='action',
            unique_together={('plan', 'identifier')},
        ),
        migrations.AlterIndexTogether(
            name='action',
            index_together={('plan', 'order')},
        ),
    ]
