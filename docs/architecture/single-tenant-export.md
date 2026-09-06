# Single-Tenant Data Export

## Overview

When a client ends their contract (or otherwise asks for their data), we need to hand
them a self-contained dump of *their* plan and nothing belonging to any other tenant.
The `export_plan` management command produces that dump as JSON in Django's standard
serialization format — the same format `dumpdata` emits and `loaddata` consumes.

The export is **non-destructive** and **read-only**: it does not touch the database, and
it does not require making a throwaway copy of the whole database first.

## Why not `destructively_trim_db` + `dumpdata`?

The pre-existing way to produce a single-tenant dump is destructive: copy the entire
database, run `destructively_trim_db --exclude-plan X --prune-shared-reference-data` to
delete every other tenant, then `dumpdata` the survivors.

That is a **denylist**: "delete everything that isn't this plan, and hope nothing leaks."
It is fragile by construction. Deleting a plan leaves behind orphaned Wagtail page trees,
`wagtail_localize` translation metadata (which carries the *source text* of deleted
objects), and shared common-indicator library data — each of which had to be cleaned up
by hand-written passes (see `delete_orphaned_plan_pages`, `delete_orphaned_translation_data`,
and `prune_unused_common_indicators` in `src/actions/management/commands/destructively_trim_db.py`).
Every new model or relation risks a new leak that the cleanup code has to catch up to.

`export_plan` is instead an **allowlist**: it walks *only* the objects that provably
belong to the plan and serializes those. Because it never visits another tenant's rows,
it cannot leak them — the guarantee is structural, not the result of chasing orphans.

## Reusing the `copying` app

The `copying` app already solves the harder inverse problem — deep-cloning a plan into an
independent copy — and in doing so it maintains a precise, declarative description of what
belongs to a plan. The export reuses that description.

The `copying` app has two separable halves:

| Half | Symbols | Export reuses? |
|------|---------|----------------|
| **Scope definition + traversal** | `PLAN_CLONE_STRUCTURE` (and the `ATTRIBUTE_TYPE_`/`INDICATOR_`/`DIMENSION_`/`DATASET_SCHEMA_` structures), `visit_tree`, `iter_plan_owned_instances`, `ConfigurableRelationTree`/`RelationTreeIterator` (from the `relations_iterator` package) | **Yes** |
| **Deep-copy + reference remapping** | `CloneVisitor`, `UpdateReferencesVisitor`, `UNIQUE_FIELD_COPY_POLICIES`, cycle-breaking, StreamField/rich-text reference rewriting | **No** |

Everything that makes `copy_plan` complicated exists to produce an *independent* copy:
remapping foreign keys to the cloned objects, regenerating unique values, breaking and
restoring reference cycles. An export preserves primary keys verbatim, so there is nothing
to remap, no unique constraints to juggle, and no cycles to break. We reuse the scope
definition and the traversal engine, and discard the entire copy/remap machinery.

### The clone structures

`PLAN_CLONE_STRUCTURE` is a nested dict keyed by Django relation accessor names. A nested
dict means "traverse into this relation"; the `EXCLUDED` sentinel means "stop here". The
`relations_iterator` engine (`ConfigurableRelationTree` + `RelationTreeIterator`) walks the
tree from a root instance and yields every reachable instance. `iter_plan_owned_instances`
wraps this, deduplicating by `(type, pk)`, and additionally pulls in:

- GFK-scoped **attribute types** (`_get_attribute_types_for_copying`), which aren't reachable
  by accessor traversal because they use generic foreign keys;
- **indicators** and their **dimensions**/**dataset schemas** (via the `INDICATOR_`,
  `DIMENSION_`, `DATASET_SCHEMA_` structures).

## Export scope differs from copy scope

Many `EXCLUDED` entries in `PLAN_CLONE_STRUCTURE` are excluded **because they are hard to
*remap* when copying**, not because they aren't plan-owned. For a PK-preserving export those
should be re-included. The export therefore defines its own `EXPORT_PLAN_STRUCTURE`, derived
from `PLAN_CLONE_STRUCTURE` with these reclassifications:

| Relation | Excluded from copy because… | Export decision |
|----------|------------------------------|-----------------|
| `report_types.reports` | Action snapshots embed original PKs → remapping nightmare | **Include** — PKs preserved, snapshots stay valid |
| `*changelogmessage*` | Not needed for a copy | **Include** (history) |
| `pledges.commitments`, `pledges` | Depend on citizen approval | Include behind `--include-pledges` |
| `user_feedbacks` | Not needed for a copy | Include behind `--include-feedback` |
| `contact_persons.notification_preferences` | Personal runtime state | Include behind `--include-feedback` (PII-adjacent) |
| `domains` | Hostname must be unique per plan | **Drop** (client provisions their own) |
| `monitoring_quality_points` | Legacy | **Drop** |
| `mcp_write_authorization_grants` | Our-side auth grants | **Drop** |
| `children` / `superseded_plans` / `copies` | These are *other* plans | **Drop** (correct as-is) |
| page relations (`category_pages`, `documentation_root_pages`, `level_layouts`, `actionlistpage`, site root tree) | Wagtail's `Page.copy` handles them | Handled separately (see below) |

A **coverage test** asserts that every model reachable from a plan is either exported,
gated behind a named flag, or listed in an explicit "intentionally dropped" set — so a
future schema change fails loudly instead of silently under- or over-exporting.

## Things the clone structures deliberately skip

Copy delegates these to Wagtail / bespoke code rather than the relation tree; the export
collects them as raw rows:

- **Wagtail pages** — the plan's site root page plus all its translations and their
  descendants, and every `DocumentationRootPage` tree. Pages use multi-table inheritance,
  so each page contributes **two rows**: the base `wagtailcore.page` row and the
  concrete-subclass row. Treebeard `path`/`depth` are ordinary columns, so tree ordering
  survives serialization.
- **Collections + media rows** — the plan's `root_collection` subtree, plus the
  `AplansImage`/`AplansDocument` rows in those collections. The binary files live in object
  storage; the JSON only references their paths. Use `--media-manifest` to also emit the
  list of storage keys to ship alongside (logic shared with `migrate_s3_files.py`).
- **Revisions / log entries** — dropped by default (clean-slate handoff, matching copy).

## Reference-consistency closures (always on)

The relation-tree traversal is keyed on plan *ownership*, but some exported rows reference
plan-ownable objects that aren't formally owned by the plan. Left alone these become dangling
foreign keys in the dump, so the export closes over them (independently of the shared-object
question below):

- **Referenced indicators (and their dimensions).** Exported `ActionIndicator` /
  `IndicatorCategoryThrough` rows can point at indicators that aren't in `plan.indicators`
  (e.g. an indicator attached to an action but never added to the plan — in practice these
  are often orphaned indicators belonging to *no* plan). Those indicators are pulled in via
  `INDICATOR_CLONE_STRUCTURE`, which drags in their values, which reference dimension
  categories — so the referenced dimensions are closed over via `DIMENSION_CLONE_STRUCTURE`
  too. This runs to a fixpoint. **Isolation guard:** an indicator or dimension owned by a
  *different* plan is skipped, so only orphaned or this-plan objects are pulled in; the far
  end of a genuine cross-tenant reference is intentionally left dangling rather than leaked.
- **Referenced media.** Images/documents are otherwise collected by collection membership,
  but pages and rich-text/StreamField bodies can reference media in *other* collections (a
  page header image, an embedded image). Those are found via forward references **and
  Wagtail's `ReferenceIndex`** (which is the only way to see references embedded in rich
  text/StreamField), and their collection rows are pulled in so the collection FK resolves.

## Referenced shared objects

Models in `MODELS_NOT_COPIED` (`Organization`, `Person`, `User`, `Client`, `CommonIndicator`,
`CommonCategory[Type]`, `Quantity`, `Unit`, `Locale`, `Group`, `ContentType`,
`DatasetDimension`) are **referenced by primary key but not part of the plan**. The export
leaves those references as PK / natural-key references in the output.

The intended use is portability/archival — "hand the client their data" — not a guaranteed
one-shot `loaddata` into a *completely empty* database. So the export does **not** compute a
full transitive closure over global models.

For readability, `--include-referenced-shared-objects` does a **one-level** pull of the shared
rows directly referenced by the plan-owned set (via FK, generic FK or M2M) so org/person/
indicator names are present rather than bare PKs. It does not follow those objects' own
relations — that is what would drag another tenant's data in — **with one deliberate
exception: `Organization` ancestors are followed transitively**, so the org hierarchy isn't
truncated to just the referenced nodes. Off by default.

Note that even with the flag on, a few second-order references remain external by design:
`auth.Permission` (referenced from the pulled-in `Group`s; a framework table present in every
Django database and serialized by natural key), and the avatars/logos/pages hanging off the
pulled-in shared objects (not followed, per the one-level rule).

## Serialization

`django.core.serializers.serialize('json', instances, indent=2, use_natural_foreign_keys=True)`
— the same machinery `dumpdata` uses. Natural foreign keys keep `ContentType`/`Permission`
references portable across databases where those PKs differ. `loaddata` loads within a single
transaction with deferred constraint checking, so cross-FK ordering is largely a non-issue;
the one thing to get right is emitting both the base and concrete rows for MTI pages.

## Usage

```
python manage.py export_plan <identifier> \
    [--output plan.json] \
    [--no-indicators] \
    [--include-pledges] \
    [--include-feedback] \
    [--include-referenced-shared-objects] \
    [--include-audit-logs] \
    [--media-manifest media.json]
```

Defaults: plan content + staff contacts + pages + collections/media rows + reports +
change-log history; citizen pledges, user feedback, notification preferences, revisions,
and audit logs are excluded unless their flag is given.

## Code layout

- `src/copying/main.py` — existing clone structures and `iter_plan_owned_instances` (reused).
- `src/copying/export.py` — `EXPORT_PLAN_STRUCTURE`, page/collection/media collectors, the
  reference-consistency closures (referenced indicators/dimensions, referenced media), the
  shared-object pull, and the serializer.
- `src/copying/management/commands/export_plan.py` — the command.
- `src/copying/tests/test_export.py` — coverage, tenant-isolation, and round-trip tests.
