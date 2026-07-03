from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand, CommandError

from actions.models.plan import Plan
from copying.export import (
    build_export_plan_structure,
    build_media_manifest,
    collect_export_instances,
    serialize_plan,
)

if TYPE_CHECKING:
    from argparse import ArgumentParser


class Command(BaseCommand):
    help = "Export a single plan's data as JSON (dumpdata format) for handing over to a tenant"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument('identifier', help='Identifier of the plan to export')
        parser.add_argument(
            '--output',
            help='Write the JSON dump to this file (default: stdout)',
        )
        parser.add_argument(
            '--no-indicators',
            action='store_false',
            dest='include_indicators',
            help="Do not export the plan's indicators, dimensions and dataset schemas",
        )
        parser.add_argument(
            '--include-pledges',
            action='store_true',
            help='Include citizen pledge commitments (personal data)',
        )
        parser.add_argument(
            '--include-feedback',
            action='store_true',
            help='Include user feedback and notification preferences (personal data)',
        )
        parser.add_argument(
            '--include-audit-logs',
            action='store_true',
            help='Include plan-scoped audit log entries',
        )
        parser.add_argument(
            '--include-referenced-shared-objects',
            action='store_true',
            help=(
                'Also include a shallow copy of directly-referenced shared objects (organizations, persons, '
                'common indicators, ...) so the dump is interpretable without a base install'
            ),
        )
        parser.add_argument(
            '--media-manifest',
            help='Also write a JSON manifest of referenced media file keys (images, documents, avatars) to this file',
        )

    def handle(self, *args, **options) -> None:
        try:
            plan = Plan.objects.get(identifier=options['identifier'])
        except Plan.DoesNotExist:
            raise CommandError(f"No plan with identifier '{options['identifier']}' exists.") from None

        structure = build_export_plan_structure(
            include_pledges=options['include_pledges'],
            include_feedback=options['include_feedback'],
            include_audit_logs=options['include_audit_logs'],
        )

        data = serialize_plan(
            plan,
            structure=structure,
            include_indicators=options['include_indicators'],
            include_referenced_shared_objects=options['include_referenced_shared_objects'],
        )

        output_path = options['output']
        if output_path:
            Path(output_path).write_text(data)
            self.stderr.write(self.style.SUCCESS(f'Wrote plan export to {output_path}'))
        else:
            self.stdout.write(data)

        manifest_path = options['media_manifest']
        if not manifest_path:
            return
        # Rebuild the instance list to derive the media manifest (cheap relative to serialization).
        instances = collect_export_instances(
            plan,
            structure=structure,
            include_indicators=options['include_indicators'],
            include_referenced_shared_objects=options['include_referenced_shared_objects'],
        )
        manifest = build_media_manifest(instances)
        Path(manifest_path).write_text(json.dumps(manifest, indent=2))
        counts = ', '.join(f'{len(v)} {k}' for k, v in manifest.items())
        self.stderr.write(self.style.SUCCESS(f'Wrote media manifest ({counts}) to {manifest_path}'))
