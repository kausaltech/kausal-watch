"""
Fill the reports of each report comparison block with the reports it has shown until now.

Until plan 3, Phase C, a block compared the five latest reports of its template that were marked public. The blocks
now list their reports, and `Report.is_public` is removed after this migration. Drafts in page revisions are filled
too, so publishing one later shows the same reports.
"""

import json
import uuid

from django.db import migrations
from django.db.models import F, JSONField
from django.db.models.functions import Cast
from wagtail.blocks import StreamValue

STREAM_FIELDS = ('details_main_top', 'details_main_bottom')
MAX_REPORTS_TO_COMPARE = 5


class ReportComparisonFiller:
    def __init__(self, apps):
        self.Report = apps.get_model('reports', 'Report')
        self.report_pks_by_type: dict[int, list[int]] = {}

    def report_items(self, report_type_id) -> list[dict]:
        if not isinstance(report_type_id, int):
            return []
        if report_type_id not in self.report_pks_by_type:
            self.report_pks_by_type[report_type_id] = list(
                self.Report.objects
                .filter(type_id=report_type_id, is_public=True)
                .order_by('-start_date')
                .values_list('pk', flat=True)[:MAX_REPORTS_TO_COMPARE]
            )
        # Each list item needs an ID of its own
        return [{'type': 'item', 'value': pk, 'id': str(uuid.uuid4())} for pk in self.report_pks_by_type[report_type_id]]

    def fill(self, stream_data) -> bool:
        """Add the reports to the report comparison blocks of the raw stream data; return whether any were added."""
        if not isinstance(stream_data, list):
            return False
        changed = False
        for child in stream_data:
            if not isinstance(child, dict) or child.get('type') != 'report_comparison':
                continue
            value = child.get('value')
            if not isinstance(value, dict) or 'reports' in value:
                continue
            value['reports'] = self.report_items(value.get('report_type'))
            changed = True
        return changed


def fill_pages(apps, filler: ReportComparisonFiller):
    ActionListPage = apps.get_model('pages', 'ActionListPage')
    for name in STREAM_FIELDS:
        stream_block = ActionListPage._meta.get_field(name).stream_block
        pages = ActionListPage.objects.annotate(raw_content=Cast(F(name), JSONField())).filter(raw_content__isnull=False)
        for page in pages:
            if filler.fill(page.raw_content):
                setattr(page, name, StreamValue(stream_block, page.raw_content, is_lazy=True))
                page.save(update_fields=[name])


def fill_revisions(apps, filler: ReportComparisonFiller):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Revision = apps.get_model('wagtailcore', 'Revision')
    content_type = ContentType.objects.filter(app_label='pages', model='actionlistpage').first()
    if content_type is None:
        return
    for revision in Revision.objects.filter(content_type=content_type).iterator():
        changed = False
        for name in STREAM_FIELDS:
            # Revisions store the stream data as JSON text
            raw = revision.content.get(name)
            stream_data = json.loads(raw) if isinstance(raw, str) else raw
            if filler.fill(stream_data):
                revision.content[name] = json.dumps(stream_data) if isinstance(raw, str) else stream_data
                changed = True
        if changed:
            revision.save(update_fields=['content'])


def fill_reports(apps, schema_editor):
    filler = ReportComparisonFiller(apps)
    fill_pages(apps, filler)
    fill_revisions(apps, filler)


class Migration(migrations.Migration):
    dependencies = [
        ('pages', '0075_report_comparison_reports'),
        ('reports', '0022_report_template_description'),
        ('wagtailcore', '0094_alter_page_locale'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.RunPython(fill_reports, migrations.RunPython.noop),
    ]
