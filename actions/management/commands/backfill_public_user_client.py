from __future__ import annotations

from django.core.management.base import BaseCommand

from actions.models.public_user import PublicUser


class Command(BaseCommand):
    help = (
        "Bind legacy anonymous PublicUsers to a client based on their commitments' "
        "pledge.plan primary ClientPlan. Idempotent; re-run after marking a "
        'ClientPlan as primary on plans that were unconfigured when migration 0187 ran.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would change without writing.',
        )

    def handle(self, *args, dry_run: bool = False, **options):
        candidates = PublicUser.objects.filter(client__isnull=True, email__isnull=True)
        bound = 0
        skipped_no_signal = 0
        skipped_ambiguous = 0
        for user in candidates.iterator():
            client_ids = set(
                user.commitments.filter(pledge__plan__clients__is_primary=True).values_list(
                    'pledge__plan__clients__client_id', flat=True,
                )
            )
            if len(client_ids) == 1:
                client_id = client_ids.pop()
                if not dry_run:
                    user.client_id = client_id
                    user.save(update_fields=['client'])
                bound += 1
            elif not client_ids:
                skipped_no_signal += 1
            else:
                skipped_ambiguous += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'Anon {user.uuid} has commitments across {len(client_ids)} clients; skipped.'
                    )
                )

        prefix = '[dry-run] would bind' if dry_run else 'Bound'
        self.stdout.write(self.style.SUCCESS(f'{prefix} {bound} anons.'))
        self.stdout.write(f'Skipped {skipped_no_signal} with no derivable client.')
        if skipped_ambiguous:
            self.stdout.write(f'Skipped {skipped_ambiguous} with ambiguous cross-client commitments.')
