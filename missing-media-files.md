# Missing and shared media files: investigation and repair

Working notes for cleaning up the media damage on the production clusters. The reference
documentation for the subsystem lives in [docs/media-integrity.md](docs/media-integrity.md); this
file is the operational plan — what is known, what to run, and in what order.

Related: PR #647 (`fix/shared-media-file-deletion`), Sentry `WATCH-BACKEND-8SF`.

## 1. The problem

Two database rows ended up pointing at a single S3 object. Deleting either row then deleted the
file out from under the other, leaving the survivor with a dangling reference — the 404s in Sentry.

### Why the keys collided

Django's `Storage.get_available_name()` is what normally stops two uploads of the same filename from
clobbering each other: it appends a random suffix when the requested name is taken. django-storages
defaults `file_overwrite` to `True` for S3, which switches that off — `get_available_name()` hands
back the requested key even when another object already occupies it.

Because the upload path is a pure function of the filename (plus, for images, the creation month),
two uploads of the same name resolve to one key.

### Three code paths that produced it

**Chooser re-uploads.** An editor uploads a file that already exists. It silently overwrites the
existing object, because the key collides. Wagtail then hashes it, notices the contents match, and
offers "use the existing image"; confirming deletes the row it just created — along with the file
both rows point at. Reconstructed from `LoggedRequest` on **de-prod**, 30 July (fi-prod's image 9257
is a different file that happens to share the PK — easy to conflate):

```
12:54:04  POST /admin/images/chooser/create/   "Landwirtschaft_ohne Credis_Canva.jpg"  → creates 9269
12:54:09  POST /admin/images/9269/delete/?next=…/chooser/chosen/9257/                  → 9257 loses its file
12:56:04  first 404 for image 9257
```

**Copying a plan's collection.** `copy_collection_with_contents` (`copying/main.py`) copies a file by
re-saving its bytes under the same name:

```python
content_file = ContentFile(file.read(), name=file.name)
file.save(filename, content_file)
```

With `file_overwrite=True` that writes over the source and leaves both rows on one key. The ID
pattern in fi-prod's output makes this one unmistakable — a contiguous block of new document IDs
mapping onto scattered older ones: `(346,676) (351,677) (389,678) (392,679) (457,680) …`. The plan
identifiers confirm it: `san-diego-cap` → `san-diego-cap-copy1`, `stpaul-carp` → `stpaul-carp-2026`.
Documents land in a flat `documents/` prefix with no date directory, which is why they collide far
more than images: 95 shared groups against 16 across the four clusters.

**The copies are byte-identical, so this path lost no content** — the rows just need keys of their
own. The triage confirmed this empirically: 100 of the 111 shared keys have rows that agree on their
recorded hash.

**Filename truncation.** `truncate_filename` (`images/models.py:23`) trims an upload path to 94
characters, with the date directory already in it. `original_images/YYYY-MM/` eats 24, so filenames
are cut to 70 — and two different images agreeing for their first 66 characters collide. us-prod's
`Energy_Use_of_Benchmarking_Building_Compared_to_all_Commercial_and.JPG` and
`Greenhouse_Gas_Emissions_from_Benchmarking_Buildings_Compared_to_C.JPG` are both exactly 94
characters with their directory, each having eaten a different chart. This path is the nastiest of
the three: no duplicate-detection prompt, no copy operation, nothing in the UI to suggest anything
happened.

### Two distinct consequences

1. **Deleting either row destroys the other's file.** This is the one Sentry sees.
2. **The earlier row's content was already destroyed at upload time**, silently, if the two uploads
   had different bytes. No error, nothing in the database flags it. A shared key is not only a
   future hazard; it may be data loss that happened months ago.

### What stops it recurring

Both fixes had to be **deployed**, not merely merged, before any repair. They went out with
423552039 on 2026-08-24, and `file_overwrite` reads `False` on all four clusters:

- `file_overwrite=False` in `kausal_common`, restoring filename de-duplication. This closes all three
  paths above, truncation included: the suffix is applied after the name is trimmed.
- A guarded `post_delete` handler that re-checks at commit time whether another row still references
  the file, and skips the delete if so. This protects collisions that already exist in the database,
  which the storage change alone does not.

Every shared key found in the scans predates that deploy, including the 2026-08 ones, so nothing
new is still colliding.

## 2. The commands

All four live in `images/management/commands/`. They cover documents as well as images.

### `check_media_integrity`

*Finds the damage.* Reports files missing from storage and files that more than one object points
at. Lists each directory once rather than querying per file, and exits non-zero on findings so it
can run from cron.

```
--include-renditions    also check image renditions (regenerable, but a shared rendition key is the
                        same time bomb)
```

### `triage_shared_media`

*Sorts the damage by what it will cost*, from the database alone — no S3, no version history, seconds
to run. Compares the `file_hash` and `file_size` the rows on a key recorded (`SAME` / `DIFFER` /
`UNKNOWN`) and attributes every row to a plan through `Plan.root_collection`. Run this before the
inventory: on production it moved 90% of the shared keys into "needs no recovery at all".

```
--emit-keys DIR     write same-keys.txt, differ-keys.txt, unknown-keys.txt, residue-keys.txt and
                    (with --include-missing) missing-keys.txt, ready for --keys-file
--include-missing   also attribute the rows whose file is gone; needs `s3:ListBucket`
```

### `inventory_media_versions`

*Decides what is recoverable*, read-only, by joining each affected key's S3 version history against
what the database rows recorded (`file_hash`, `file_size`). Classifies each key as `lossless`,
`overwritten`, `unknown-hashes`, `missing` or `intact`, and says whether every row could be given
back the bytes it recorded.

```
--verify-hashes     download candidate versions and compare SHA-1 against file_hash. Slower but
                    authoritative; without it versions are matched on recorded size and the report
                    says "(size-matched only)"
--keys-file PATH    inventory only these `file` values, one per line, skipping discovery
--json PATH         write the full report as JSON
```

Version history is not necessarily readable with the application's own credential. When
`MEDIA_RECOVERY_S3_ACCESS_KEY_ID` and `MEDIA_RECOVERY_S3_SECRET_ACCESS_KEY` are set they are used
*only* for the versioning API; discovery still goes through the application's storage. No cluster
needs that split any more — see the Hetzner policy fix in section 3.

### `repair_media_files`

*Applies the repair.* **Dry-run by default**; `--execute` is required to write anything.

```
--execute           actually copy objects and update rows
--only shared       repair only shared keys
--only missing      repair only files missing from storage
--keys-file PATH    repair only these `file` values, skipping discovery
```

Shared keys: the row matching the current bytes keeps the key, every other row gets a fresh key
holding the version it originally uploaded. Missing files: the version matching the row's
`file_hash` is copied forward as a new current version, rather than the delete marker being removed.

Safety properties worth knowing before running it with `--execute`:

- **Versions are matched by hash, never by recency.** Where a sibling overwrote a key before being
  deleted, the newest surviving version holds the *sibling's* bytes.
- **Repair of a shared key is all-or-nothing**, in planning and in execution. A group that cannot be
  fully traced is reported, not half-repaired.
- **It refuses to run while `file_overwrite=True`**, because it could not allocate distinct keys.
- Unresolvable groups are reported and skipped rather than guessed at.

### Producing a keys file

`triage_shared_media --emit-keys DIR --include-missing` writes them: `same-keys.txt`,
`differ-keys.txt`, `unknown-keys.txt`, `missing-keys.txt`, `residue-keys.txt`. One `file` value per
line — the database column value, not the bucket key. Each run rewrites all of them, empty ones
included, so a verdict that no longer has findings cannot leave a stale file behind to be repaired
twice; `missing-keys.txt` is deleted outright when `--include-missing` was not passed.

To scope a re-run from an inventory instead:

```fish
jq -r '.[].entries[] | select(.kind != "intact") | .file' /tmp/inventory.json > /tmp/keys.txt
```

## 3. Storage situation per cluster

| | fi-prod | de-prod | us-prod | ca-prod |
|---|---|---|---|---|
| Backend | MinIO, `s3.kausal.tech` | Hetzner, `fsn1.your-objectstorage.com` | Hetzner, same endpoint | Hetzner, same endpoint |
| Bucket | `watch-media-prod` | `kausal-watch-media-de` | `kausal-watch-media-us` | `kausal-watch-media-ca` |
| Versioning | enabled | enabled | enabled | enabled |
| Lifecycle rules | none | none | none | none |
| App key reads version history | yes | yes, since 2026-08-26 | yes, since 2026-08-26 | yes, since 2026-08-26 |

No lifecycle rules means nothing expires noncurrent versions, so history reaches back to whenever
versioning was switched on. **Every cluster has a recovery path.**

Every cluster has its own bucket, confirmed per cluster from `default_storage`. This matters: the
delete guard and the repair's idea of "every row on this key" are both scoped to one database, so a
shared bucket would have defeated both silently.

### The Hetzner policy fix

All three Hetzner buckets denied `ListObjectVersions` to their application credential — not a
de-prod misconfiguration as first assumed, but how the buckets were provisioned. This blocked *every*
shared-key repair, not just the ones needing recovery, because `unshare` lists versions before doing
anything and every copy it makes pins a `VersionId`.

Fixed on 2026-08-26 by adding `s3:ListBucketVersions` and `s3:GetBucketVersioning` to the existing
bucket-level statement for the app principal in each of the three policies. The object-level
statement already granted `s3:*`, which covers `s3:GetObjectVersion`. Backups of the previous
documents are at `/tmp/{ca,de,us}-policy.new.json`.

No policy grants anonymous read — no statement names `Principal: "*"` — so a policy replacement
cannot take the public site down. Media reaches browsers through presigned URLs: on fi-prod an
unsigned GET returns 403 for both an original and a repaired copy, while `file.url` returns a signed
URL. The `public-read` ACL that `MediaFilesS3Storage` sets is therefore vestigial there;
`repair_media_files` passes it on every copy regardless, so a copy is never less reachable than its
original. Confirm with an unsigned GET before assuming the same on the Hetzner clusters.

`MEDIA_RECOVERY_S3_*` is no longer needed anywhere.

## 4. Where each cluster's damage belongs

fi-prod seeded the other three, so the same damaged rows recur across clusters with identical PKs.
`PlanDomain` was seeded along with everything else, so fi-prod still claims
`climatedashboard.sandiego.gov`, `klima-monitor.potsdam.de`, `ziele.ludwigsburg.de` and the Köln
hostnames — but DNS resolves all of them to `watch-prod.us` or `watch-prod.de`. **Check DNS, not
`PlanDomain`.** fi-prod's copies of those four plans are stale; its only live hostname among them is
`san-diego-cap.watch-test.kausal.tech`.

State after the 2026-08-26 repairs:

| cluster | `SAME` repaired | `SAME` left | `DIFFER` | missing | problems now |
|---|---|---|---|---|---|
| ca-prod | 2 | 1 residue | 1 | 2 | 4 |
| de-prod | 9 | 1 residue | 3 | 6 | 10 |
| fi-prod | 17 | 23 (22 migrated + residue) | 3 | 19 | 45 |
| us-prod | 46 | 1 residue | 4 | 2 | 7 |
| **total** | **74** | **26** | **11** | **29** | **66** |

Every migrated-tenant group is `SAME`, so fi-prod's stale-plan question gates nothing expensive — it
only decides whether 22 cheap copies in fi-prod's bucket are worth making. They probably are: while
those findings stand, `check_media_integrity` exits non-zero on them, which is what prevents using
it as a CronJob alert.

The `Bilanzteil` pairs `[425, 426]` live in the shared `Common Categories` collection — framework
content rather than any plan's, which is how they reached all four clusters — and nothing references
either row. Delete *one* row per cluster rather than repairing or deleting both: the key stops being
shared, and the guard keeps the file because the survivor still points at it, so nothing leaves
storage. `refscan.py` is the reference check; it pairs `ReferenceIndex` with a raw column scan,
because the index covers Pages, Categories, Reports and other registered models but not `Action`,
`Indicator`, the attribute value models or draft revisions.

### The 11 keys that lost content

| cluster | key | rows | plan |
|---|---|---|---|
| fi | `2026-06/Screenshot_2026-06-29_152048.png` | 9315 / 9316 | albany-climate |
| fi | `2026-07/Solar_Panel_Pictures1.jpg` | 10125 / 10126 | stevenage-cap |
| fi | `StR-Beschluss_293-2025…Wärme_2030.pdf` | 719 (2025-11) / 846 (2026-03) | kloten-klima |
| de | `2026-05/Endenergieverbrauch_Verkehr.png` | 9123 / 9126 | NO-PLAN |
| de | `260706_KSPfade_Wärme_EE_Update.docx.pdf` | 912 / 917 | klimaschutz-nrw |
| de | `260707_KSPfade_GründungenStartUps_Update.docx.pdf` | 927 / 928 | klimaschutz-nrw |
| us | `…Compared_to_all_Commercial_and.JPG` | 8118 / 8236 | stpaul-carp-2026 |
| us | `…Compared_to_C.JPG` | 8119 / 8237 | stpaul-carp-2026 |
| us | `2026-06/Hamline_Library_solar_project_graphic.jpg` | 8296 / 8298 | stpaul-carp-2026 |
| us | `2026-08/Document.png` | 8473+8474 / 8475 / 8476 / 8477+8478 | westminster-sap |
| ca | `2026-08/Switch.jpg` | 9324 / 9326 | charlottetown-cap |

26 rows, 13 distinct contents to recover. `Document.png` is the hardest: six rows, four contents, one
key, from a scanner's default filename.

`inventory_media_versions --verify-hashes` on 2026-08-26 found **all 11 recoverable**: every row
traces to a stored version by hash, so nothing among the shared keys is permanently lost. The only
non-trivial history is `260707_KSPfade_GründungenStartUps_Update.docx.pdf` on de-prod — 3 versions
and 1 delete marker, the marker not current.

Two things differ from the `SAME` repairs. The keeper is the row matching the *current* bytes, so it
is often not the lowest PK. And for the 8 image groups, renditions must be purged afterwards for
every row in the group, keeper included — restoring content does not invalidate them, since
`file_hash` is unchanged and both the rendition lookup and its cache key are content-blind.

Several of these are an editor uploading a corrected version months later — `912/917`, `927/928`,
`719/846`, probably `9324/9326`. The repair will faithfully restore the *older* bytes to the older
row, which is correct by construction but may not be what anyone wants; check what references those
rows first. The two truncated us-prod names are the opposite case: genuinely different source images,
one of each pair simply gone.

## 5. Next steps

### Step 1 — fi-prod, one key at a time

Nothing blocks this: its app credential reads version history, and its `SAME` groups need no
recovery. This is also the first time any of these commands touches a live bucket, so start with a
single small group and read the plan rather than skimming it.

```fish
printf '%s\n' 'documents/Zero_Emisisons_Kingston_McKinna.pdf' > /tmp/fi-first.txt

kubectl --context fi-prod -n watch-backend-production exec -i deploy/watch-backend-production -- \
    sh -c 'cat > /tmp/keys.txt && python manage.py repair_media_files --keys-file /tmp/keys.txt --only shared' \
    < /tmp/fi-first.txt
```

Expect `row 216 keeps the key; 1 row(s) move`, no `(currently deleted)`, no warnings. Then the same
with `--execute`, then `check_media_integrity` to confirm the group is gone, then widen to the whole
`same-keys.txt`.

Take a database snapshot before the first `--execute`, and run during a media-quiet period: version
history can undo the S3 side, not the row updates.

### Step 2 — ca-prod, de-prod, us-prod

Same sequence, in that order — ascending size. Deploy `triage_shared_media` first so the key files
can be produced in-cluster rather than assembled by hand.

### Step 3 — the 11 keys and the 29 missing files

```fish
python manage.py inventory_media_versions --keys-file /tmp/differ-keys.txt --verify-hashes \
    --json /tmp/inventory.json
python manage.py repair_media_files --keys-file /tmp/differ-keys.txt --only shared
python manage.py repair_media_files --keys-file /tmp/missing-keys.txt --only missing
```

Run each in the cluster that actually owns the rows. Two of fi-prod's missing images
(`longmont-logo-white-small.png`, `YOLO_Icons_Public_Health.png`) belong to tenants now served from
us-prod and are missing there too, so that recovery belongs in the us bucket.

In parallel, ask the customers: Westminster for the four `Document.png` scans, Saint Paul for the two
truncated-name charts and the Hamline graphic, Charlottetown for `Switch.jpg`. Faster and more
certain than version archaeology, and independent of everything above.

### Step 4 — after the repairs

- Re-run `check_media_integrity --include-renditions` everywhere, then purge what it finds with
  `purge_renditions.py` (dry run unless `EXECUTE=1`). Renditions must be **deleted, not repaired**:
  on a shared rendition key some rows serve another image's rendering, so only regeneration fixes the
  content, and `repair_media_files` does not touch renditions anyway. ca-prod's scan found 22 shared
  keys and 1 missing file — mostly a mechanism of its own, where Wagtail truncates the original's
  stem to `59 - len(spec)` characters and collapses distinct originals onto one rendition name.
  Purge only after the originals are restored, or renditions cannot regenerate.
- Delete `documents/Bilanzteil_Koln_2019.pdf` `[425, 426]` in all four clusters — another client's
  document, owned by no plan, in three wrong regions. Check for references first.
- Drop fi-prod's stale `PlanDomain` rows for the four migrated plans. They are what made the database
  unable to answer where a plan lives.
- Close the Sentry issue only once the broken rows are dealt with.
- Add `check_media_integrity` as a CronJob. It already exits non-zero, so it is alert-ready as is.
- Add an explicit `Deny` for `s3:DeleteObjectVersion` to the app principals. The Hetzner policies
  grant `s3:*` on `bucket/*`, so version history is currently *not* tamper-proof, and an `Allow` that
  broad can only be narrowed by an explicit `Deny`.
- Decide whether the development principal should keep `readonly` access to all three production
  media buckets. `_init_hetzner_media_bucket` (pulumi) grants it deliberately, so this is a policy
  question rather than a leak.
- Consider an independent backup of the Hetzner buckets. Versioning is enabled, but there is no
  second copy anywhere.

## 6. Open risks

- **The shared-key repair is now proven on both backends**, over 74 keys and 100 rows, with every
  cluster hitting its predicted problem count and nothing left for review. What is still covered
  only by a fake client is the *recovery* path: restoring a specific noncurrent version, and the
  delete-marker handling that goes with a missing file. The fake has been wrong about real S3
  behaviour twice during review (multipart ETags, delete-marker visibility), so treat the first
  `--only missing` run the way the first `--only shared` run was treated: one key, read carefully.
- **Some groups will report `NEEDS REVIEW`** rather than being repaired. That is deliberate: the
  command declines to guess when a row cannot be traced to stored bytes. Watch for `no row matches
  the current content` on a `SAME` group — that means a since-deleted third row wrote the current
  bytes.
- **Deletions predating versioning are unrecoverable**, and that is now measured rather than feared.
  Seven files have zero versions in *any* of the four buckets: images 3941, 3952, 4660, 6255 and
  documents 463, 464, 465. Their surviving renditions all report `VersionId: null`, which dates
  versioning on `watch-media-prod` to somewhere between 2025-05 and 2026-06 — everything deleted
  after that was recoverable, everything before is gone. Salvage state: 3941 has a usable
  `max-1600x1600` rendition and 6255 a 165×165 that is probably its display size anyway; 3952 (a
  logo) and 4660 have only 165px renditions, too small, so ask the customer; the three documents have
  no fallback at all. `DGS_BF_Erklaerung.mp4` is a German sign-language asset, so escalate that one
  as an accessibility regression rather than filing it as a missing attachment. Renditions for 3952
  and 6255 survive only in fi-prod while the live rows are in us-prod, so salvaging those means
  moving bytes between clusters.
- **`SAME` is a claim about what the rows recorded**, not proof the bytes are still stored. A group
  can agree on a hash whose content is nowhere in the history, if versioning began after a sibling
  had already overwritten the key. The repair verifies against the bytes regardless.
- An oddity noticed while poking at fi-prod and not yet explained: a
  `Bericht_zum_Energieplan_der_Stadt_Kloten_2020.pdf/` *prefix* at the bucket root, where a document
  should be. It matches no upload path the code generates.
