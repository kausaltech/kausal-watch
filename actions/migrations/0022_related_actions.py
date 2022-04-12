from django.db import migrations, models
import django.db.models.deletion
import modelcluster.fields


class Migration(migrations.Migration):

    dependencies = [
        ('actions', '0021_add_plan_theme_identifier'),
    ]

    operations = [
        migrations.CreateModel(
            name='RelatedAction',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='order')),
                ('action', modelcluster.fields.ParentalKey(on_delete=django.db.models.deletion.CASCADE, related_name='related_actions', to='actions.action', verbose_name='action')),
                ('related_action', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='actions.action', verbose_name='related action')),
            ],
            options={
                'verbose_name': 'related action',
                'verbose_name_plural': 'related actions',
                'ordering': ['action', 'order'],
                'unique_together': {('action', 'related_action')},
                'index_together': {('action', 'order')},
            },
        ),
        migrations.AddField(
            model_name='action',
            name='related_actions_unordered',
            field=models.ManyToManyField(blank=True, related_name='_actions_action_related_actions_unordered_+', through='actions.RelatedAction', to='actions.Action'),
        ),
    ]
