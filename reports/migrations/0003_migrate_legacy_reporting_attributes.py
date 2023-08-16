from django.db import migrations
import reversion
import wagtail.blocks
import wagtail.fields

import actions.blocks.choosers
import reports.blocks.action_content


def migrate_data(apps, schema_editor):
    Action = apps.get_model('actions', 'Action')
    ActionSnapshot = apps.get_model('reports', 'ActionSnapshot')
    AttributeCategoryChoice = apps.get_model('actions', 'AttributeCategoryChoice')
    AttributeChoice = apps.get_model('actions', 'AttributeChoice')
    AttributeChoiceWithText = apps.get_model('actions', 'AttributeChoiceWithText')
    AttributeNumericValue = apps.get_model('actions', 'AttributeNumericValue')
    AttributeRichText = apps.get_model('actions', 'AttributeRichText')
    AttributeText = apps.get_model('actions', 'AttributeText')
    AttributeType = apps.get_model('actions', 'AttributeType')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Plan = apps.get_model('actions', 'Plan')
    Report= apps.get_model('reports', 'Report')
    ReportType = apps.get_model('reports', 'ReportType')
    Version = apps.get_model('reversion', 'Version')

    attribute_type_for_block = {}  # map block ID to created attribute type

    def get_or_create_attribute_type(block):
        at = attribute_type_for_block.get(block.id)
        if not at:
            at = AttributeType.objects.create(
                object_content_type=ContentType.objects.get_for_model(Action),
                scope_content_type=ContentType.objects.get_for_model(Plan),
                scope_id=rt.plan.pk,
                name = block.value['name'],
                format='text',
                show_in_reporting_tab=True,
            )
            attribute_type_for_block[block.id] = at
        return at

    def transform_blocks(blocks):
        # Iterating over blocks and setting the streamfield to a new list doesn't allow us to preserve the block IDs,
        # so change `blocks` in place
        for i, block in enumerate(blocks):
            if block.block_type == 'text_attribute':
                at = get_or_create_attribute_type(block)
                blocks[i] = ('attribute_type', {'attribute_type': at}, block.id)

    # Replace `text_attribute` blocks with `attribute_type` blocks in ReportType.fields and Report.fields
    # Also create attribute types for this
    for rt in ReportType.objects.all():
        transform_blocks(rt.fields)
        rt.save()
        for report in rt.reports.all():
            transform_blocks(report.fields)
            report.save()

    # Migrate attributes
    for report in Report.objects.order_by('end_date'):
        actions_with_updated_attributes = set()
        # Since attribute_type.report is truthy, report_field should also be truthy and the following filter
        # unnecessary, but some of our manually created legacy data is a bit broken
        for attribute_type in report.attribute_types.exclude(report_field__isnull=True):
            new_attribute_type = attribute_type_for_block[str(attribute_type.report_field)]
            object_ct = ContentType.objects.get(id=attribute_type.object_content_type_id)
            assert object_ct.app_label == 'actions' and object_ct.model == 'action'
            scope_ct = ContentType.objects.get(id=attribute_type.scope_content_type_id)
            assert scope_ct.app_label == 'actions' and scope_ct.model == 'plan'
            # Only text attributes should be in Kausal's DB at this point, so too lazy to make it work for other formats
            assert attribute_type.format == 'text', "Sorry, this only migrates text attributes"

            for attribute in AttributeText.objects.filter(type=attribute_type.id):
                assert attribute.content_type_id == object_ct.id  # actions.Action
                # It's possible we already have an attribute for new_attribute_type and this action, namely when an
                # attribute exists with that type in multiple reports
                AttributeText.objects.update_or_create(
                    type=new_attribute_type,
                    content_type=attribute.content_type,
                    object_id=attribute.object_id,
                    defaults={'text': attribute.text, 'i18n': attribute.i18n},
                )
                actions_with_updated_attributes.add(attribute.object_id)

            # Now hopefully it's safe to delete the old attribute type
            attribute_type.delete()

        # Mark affected actions as complete to create the action snapshots
        for action_id in actions_with_updated_attributes:
            action = Action.objects.get(id=action_id)
            # FIXME: This hack creates something like the GenericRelation fields that don't exist in historical models,
            # but it will probably break when Reversion's follow relationships for Action change.
            for field, model in [
                    ('choice_attributes', AttributeChoice),
                    ('choice_with_text_attributes', AttributeChoiceWithText),
                    ('text_attributes', AttributeText),
                    ('rich_text_attributes', AttributeRichText),
                    ('numeric_value_attributes', AttributeNumericValue),
                    ('category_choice_attributes', AttributeCategoryChoice),
            ]:
                setattr(action, field, model.objects.filter(
                    content_type=ContentType.objects.get_for_model(Action),
                    object_id=action.id
                ))
            # FIXME: Probably shouldn't use reversion but historical (`__fake__`) models (obtained by apps.get_model())
            with reversion.create_revision():
                reversion.add_to_revision(action)
            action_versions = Version.objects.filter(
                content_type=ContentType.objects.get_for_model(Action),
                object_id=action.id,
            )
            ActionSnapshot.objects.create(
                report=report,
                action_version=action_versions.first(),
            )


class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0002_add_created_explicity'),
        ('actions', '0074_change_attribute_type_fields'),
    ]

    operations = [
        # First add the new blocks to the `fields` fields of ReportType / Report, then migrate data, then remove the
        # old fields
        migrations.AlterField(
            model_name='reporttype',
            name='fields',
            field=wagtail.fields.StreamField([
                ('implementation_phase', reports.blocks.action_content.ActionImplementationPhaseReportFieldBlock()),
                ('text_attribute', wagtail.blocks.StructBlock([('name', wagtail.blocks.CharBlock(heading='Name')), ('identifier', wagtail.blocks.CharBlock(heading='Identifier'))])),
                ('attribute_type', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(label='Attribute type', required=True))])),
            ], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='report',
            name='fields',
            field=wagtail.fields.StreamField([
                ('implementation_phase', reports.blocks.action_content.ActionImplementationPhaseReportFieldBlock()),
                ('text_attribute', wagtail.blocks.StructBlock([('name', wagtail.blocks.CharBlock(heading='Name')), ('identifier', wagtail.blocks.CharBlock(heading='Identifier'))])),
                ('attribute_type', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(label='Attribute type', required=True))])),
            ], blank=True, null=True),
        ),
        migrations.RunPython(migrate_data),
        migrations.AlterField(
            model_name='reporttype',
            name='fields',
            field=wagtail.fields.StreamField([
                ('implementation_phase', reports.blocks.action_content.ActionImplementationPhaseReportFieldBlock()),
                ('attribute_type', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(label='Attribute type', required=True))])),
            ], blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='report',
            name='fields',
            field=wagtail.fields.StreamField([
                ('implementation_phase', reports.blocks.action_content.ActionImplementationPhaseReportFieldBlock()),
                ('attribute_type', wagtail.blocks.StructBlock([('attribute_type', actions.blocks.choosers.ActionAttributeTypeChooserBlock(label='Attribute type', required=True))])),
            ], blank=True, null=True),
        ),
    ]
