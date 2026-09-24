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

That UI reads its sign-in button from `loginEnabled`, but forwards it to the placeholder page only
alongside a non-empty `statusMessage`. The backend therefore still sends a message on every
`SIGN_IN_REQUIRED` hostname, and only there; without one, that UI would hide the sign-in button
from the viewers who need it. The newer UI shows the same message above its button.

The new UI does survive an older backend, which is what covers a backend rollback: it falls back
to `__typename` when it meets a status it does not recognise. That fallback cannot tell whether
signing in would help, though, so it offers sign-in on every hostname that serves no plan, where
the old UI offered it only when the plan's settings allowed it. Nothing becomes readable that
should not, but a visitor can be sent round a sign-in that leads back to the same placeholder.

## Freeze plan publication for the deploy

From capturing the baseline until the post-deploy `--verify` has passed, nobody publishes or
unpublishes a plan, changes a plan's visibility, or changes a domain's publication override.

The migration derives `visibility` once, from the state it finds. A previous-release pod that
publishes a plan after that leaves it launched but `internal`, so its site asks visitors to sign
in; the new release, for its part, does not keep the retired flag in step. Neither direction
exposes anything, and the post-deploy `--verify` would catch the drift, but the freeze avoids
having to untangle it. Publication is rare enough that this costs nothing.

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
plans = []
for plan in Plan.objects.filter(is_active=True).prefetch_related('domains'):
    visible = plan.is_visible_for_user(anon)
    plans.append({'plan': plan.identifier, 'readable_anonymously': visible})
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
print(json.dumps({'surfaces': rows, 'plans': plans}, indent=2, sort_keys=True))
```

`--verify` reads `key`, `plan`, `served_anonymously` and `launched` from each surface; `key` must
match the report's own, which is the hostname followed by the base path. `launched` is the
hostname's own launch state, so a domain whose override forces it published counts as launched
even when its plan has never been published.

`plans` covers everything a hostname row cannot: `plan(id:)`, REST, search, and the wildcard
hosts, which have no row of their own and followed `is_visible_for_user` alone on the old
revision as they follow `visibility` alone on the new one. A baseline without it is refused.

## 2. Dry-run on a restore

Restore the production database locally, capture the baseline on the old revision, migrate on
the new one, then:

```bash
python manage.py report_plan_visibility --verify baseline.json
```

It fails on any surface or plan whose change the migration does not explain, labelled `OUTAGE`
(a live site went dark, or a plan stopped being readable) or `EXPOSURE` (a dark site or a hidden
plan became readable). A plan's anonymous readability is never expected to change. Two hostname
changes are:

- a hostname that had not launched, which is the bug being fixed;
- a hostname forced to published whose plan was not readable anonymously. The override changed
  only what the hostname lookup reported; the site's own queries go through the plan's gate, so
  it never rendered for anyone there. It now asks visitors to sign in.

**Triage that list before deploying** — each entry is a site that will go dark, and any that
should stay up needs `visibility` or its publication date set by hand first.

The migration names two kinds of plan in its output, and each needs a deliberate decision:

- a plan that was scheduled for the future: its publication date is cleared, so it needs
  publishing when it is due;
- a plan with a domain forced to published that was not readable anonymously: it is left
  `internal`, so it needs making `public` if it was meant to be.

## 3. After deploying

Run `--verify` again against production, then generate the report for the end-to-end checks in
`kausal-watch-ui`:

```bash
python manage.py report_plan_visibility > visibility.json
VISIBILITY_REPORT=visibility.json npx playwright test plan-visibility   # in kausal-watch-ui
```

The e2e specs take their expectations from the report rather than restating them, so the backend
says what each address should do and the tests confirm it does.

## Rolling back

The previous release reads `published_at` and the retired
`expose_unpublished_plan_only_to_authenticated_user` column, not `visibility`. It has no way to
say *launched but internal*: any plan with a past publication date is public to it. So an
`internal` plan becomes readable by anyone after a rollback if it has launched, or if its retired
flag is false (a plan the migration made public for that reason, later made internal).

Before rolling back, list them:

```sql
SELECT p.identifier, p.published_at, f.expose_unpublished_plan_only_to_authenticated_user
FROM actions_plan p JOIN actions_planfeatures f ON f.plan_id = p.id
WHERE p.visibility = 'internal'
  AND (p.published_at <= now() OR NOT f.expose_unpublished_plan_only_to_authenticated_user);
```

For a flag that is false, set it to true, which is what `internal` means to the previous
release. For a launched plan there is no equivalent: unpublish it first, or accept that it will
be public until the new release is back.

The opposite drift is harmless: a `public` plan that has not launched, with the flag true, is
hidden by the previous release. That is an outage for its preview hosts and API, not an exposure.

## 4. Retiring the deprecated fields

A query naming a field the schema lacks fails validation as a whole, so each rename takes two
releases on the UI side:

1. Once every deployed backend has `showLoginLinkInPublicUi`, switch the UI's plan-context query
   from `allowPublicSiteLogin` to it.
2. Once that UI is deployed everywhere, delete `allowPublicSiteLogin` and `loginEnabled` from
   the schema, and stop sending the sign-in message: make `PlanDomain.status_message_for_user`
   return None again.

The UI's fallback to `__typename` for an unrecognised `domain.status` can go at the same time as
step 1: by then no deployed backend answers with the old publication statuses.

The retired `expose_unpublished_plan_only_to_authenticated_user` column is kept through this
release, because the previous release's pods still read it while the rollout is under way; drop
it in the next.
