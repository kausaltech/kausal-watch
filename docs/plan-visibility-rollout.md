# Rolling out plan visibility

The deploy procedure for the change described in
[Plan Visibility](architecture/plan-visibility.md). It exists for one release: once the steps
below have been run everywhere and the deprecated fields are gone, this file can be deleted.

The risk runs both ways — a plan that was dark becoming publicly readable, or a live site going
dark — so every hostname's answer is recorded before the deploy and compared after, by
`manage.py report_plan_visibility`.

## Order

Ship the backend first. The deployed UI gates on `__typename` and ignores `domain.status`, so
the backend is safe alone, and it closes the exposure immediately.

The new UI does survive an older backend, which is what covers a backend rollback: it falls back
to `__typename` when it meets a status it does not recognise. That fallback cannot tell whether
signing in would help, though, so it offers sign-in on every hostname that serves no plan, where
the old UI offered it only when the plan's settings allowed it. Nothing becomes readable that
should not, but a visitor can be sent round a sign-in that leads back to the same placeholder.

## 1. Capture the baseline, before deploying

On the **old** revision, against the database being migrated. That revision has neither
`Plan.visibility` nor `report_plan_visibility`, so the capture has to be run as a shell snippet.
It reuses the old code's own `is_visible_for_user`, plus the per-domain override that the old
`PlanInterface.resolve_type` applied before it, rather than restating the rules. Copy it to a file
outside the working tree and run:

```bash
python manage.py shell_plus --quiet-load -c "$(cat capture_baseline.py)" > baseline.json
```

(Pass it with `-c`: piped into standard input, `shell_plus` starts an interactive session
instead.)

```python
import json

from django.contrib.auth.models import AnonymousUser

from actions.models.plan import Plan, PublicationStatus

anon = AnonymousUser()
rows = []
for plan in Plan.objects.filter(is_active=True).prefetch_related('domains'):
    visible = plan.is_visible_for_user(anon)
    for domain in plan.domains.all():
        override = domain.publication_status_override
        if override is None:
            served = visible
            launched = plan.is_live()
        else:
            # The override decided both, whatever the plan's own state.
            served = launched = override == PublicationStatus.PUBLISHED
        rows.append({
            'key': domain.hostname + (domain.base_path or ''),
            'plan': plan.identifier,
            'served_anonymously': served,
            'launched': launched,
        })
print(json.dumps({'surfaces': rows}, indent=2, sort_keys=True))
```

`--verify` reads only `key`, `served_anonymously` and `launched`; `key` must match the report's
own, which is the hostname followed by the base path. `launched` is the hostname's own launch
state, so a domain whose override forces it published counts as launched even when its plan has
never been published.

## 2. Dry-run on a restore

Restore the production database locally, capture the baseline on the old revision, migrate on
the new one, then:

```bash
python manage.py report_plan_visibility --verify baseline.json
```

It fails on any surface whose change the migration does not explain, labelled `OUTAGE` (a live
site went dark) or `EXPOSURE` (a dark site became readable). Only one change is expected: a
hostname that had not launched, which is the bug being fixed. **Triage that list before
deploying** — each entry is a site that will go dark, and any that should stay up needs
`visibility` or its publication date set by hand first.

The migration also clears the publication date of any plan that was scheduled for the future,
and names each one in its output; those need publishing deliberately.

## 3. After deploying

Run `--verify` again against production, then generate the report for the end-to-end checks in
`kausal-watch-ui`:

```bash
python manage.py report_plan_visibility > visibility.json
VISIBILITY_REPORT=visibility.json npx playwright test plan-visibility   # in kausal-watch-ui
```

The e2e specs take their expectations from the report rather than restating them, so the backend
says what each address should do and the tests confirm it does.

## 4. Retiring the deprecated fields

A query naming a field the schema lacks fails validation as a whole, so each rename takes two
releases on the UI side:

1. Once every deployed backend has `showLoginLinkInPublicUi`, switch the UI's plan-context query
   from `allowPublicSiteLogin` to it.
2. Once that UI is deployed everywhere, delete `allowPublicSiteLogin` and `loginEnabled` from
   the schema.

The UI's fallback to `__typename` for an unrecognised `domain.status` can go at the same time as
step 1: by then no deployed backend answers with the old publication statuses.

The retired `expose_unpublished_plan_only_to_authenticated_user` column is kept through this
release, because the previous release's pods still read it while the rollout is under way; drop
it in the next.
