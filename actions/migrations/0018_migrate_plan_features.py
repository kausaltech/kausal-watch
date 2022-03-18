from django.db import migrations


def migrate_plan_features(apps, schema_editor):
    Plan = apps.get_model('actions', 'Plan')
    PlanFeatures = apps.get_model('actions', 'PlanFeatures')
    pf_fields = {f.name: f for f in PlanFeatures._meta.fields}
    REVERSE_FIELDS = {
        'hide_action_identifiers': 'has_action_identifiers',
        'hide_action_official_name': 'has_action_official_name',
        'hide_action_lead_paragraph': 'has_action_lead_paragraph',
        'contact_persons_private': 'public_contact_persons',
    }
    for plan in Plan.objects.all():
        if PlanFeatures.objects.filter(plan=plan).exists():
            continue
        pf = PlanFeatures(plan=plan)
        for f in plan._meta.fields:
            if f.name in ('id',):
                continue
            if f.name in pf_fields:
                val = getattr(plan, f.name)
                setattr(pf, f.name, val)
                continue
            rf = REVERSE_FIELDS.get(f.name)
            if rf is not None:
                val = not getattr(plan, f.name)
                setattr(pf, rf, val)
        pf.save()


class Migration(migrations.Migration):
    dependencies = [
        ('actions', '0017_add_plan_features_model'),
    ]

    operations = [
        migrations.RunPython(migrate_plan_features),
        migrations.RemoveField(
            model_name='plan',
            name='allow_images_for_actions',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='show_admin_link',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='hide_action_identifiers',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='hide_action_official_name',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='hide_action_lead_paragraph',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='contact_persons_private',
        ),
        migrations.RemoveField(
            model_name='plan',
            name='has_action_primary_orgs',
        ),
    ]
