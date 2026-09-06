# Media file integrity

How Wagtail images and documents came to share S3 objects, what that broke, and how to find and
repair it.

## The problem

Django's `Storage.get_available_name()` is what stops two uploads of the same filename from
clobbering each other: it appends a random suffix when the requested name is taken. django-storages
defaults `file_overwrite` to `True` for S3, which turns that off — `get_available_name()` hands back
the requested key even when another object already occupies it.

The result is that two rows end up pointing at one S3 object, with two distinct consequences:

1. **Deleting either row destroys the other's file.** Wagtail's `post_delete` handler removes the
   object unconditionally, so the surviving rows are left with dangling references.
2. **The earlier row's content was already destroyed at upload time**, silently, if the two uploads
   had different bytes. The second upload overwrote the first. No error, no warning.

The second one is easy to miss: a shared key is not only a future hazard, it may already be data
loss that happened months ago.

### The code paths that caused it

**Chooser re-uploads.** Uploading a file whose name already exists writes over the existing object.
Wagtail then notices the contents match and offers to reuse the existing image; confirming that
deletes the row it just created — along with the file both rows point at. Reconstructed from
`LoggedRequest` on de-prod, 30 July 2026: a `chooser/create/` POST created a new image, a
`.../delete/?next=.../chooser/chosen/<other-pk>/` POST five seconds later took the file away from
the image being chosen, and the first 404 for it followed two minutes after that. The `next`
parameter in the delete URL is what identifies this sequence in a request log.

**Plan copying.** `src/copying/main.py:copy_collection_with_contents` duplicates a collection's images
and documents with `file.save(filename, content_file)`. With `file_overwrite=True`, that "copy"
wrote straight over the source object and left both rows on one key. This is much the largest cause
by volume, and it is recognisable in the data: the affected PKs come in contiguous blocks mapping
onto scattered older PKs, rather than in same-session pairs, and the two plans differ by a
`-copy1`-style suffix. Copying a plan is also how tenants were moved between clusters, which is why
the regional clusters inherited both the originals and the copies (see Cluster ancestry below).

**Deleting a copied plan's source.** The worst single loss found had this shape: a plan was created
by copying another, so its rows pointed at the source's objects, and the source plan was then
deleted. `Plan.delete()` cascades to `root_collection.delete()` (`src/actions/models/plan.py:1499`),
which deletes the source's documents and — before the guard existed — their files, leaving the
copy's rows dangling. It is recognisable in the data as one collection losing every file it holds
while its siblings are intact, and as a `-copy1` plan with no original. This is the case the
`post_delete` guard exists for, and the only one of these mechanisms where the storage change alone
would not have helped.

**Filename truncation.** `src/images/models.py:truncate_filename` trims an upload path to 94 characters
so it fits the `file` column, and the date directory is already part of the path when it does
(`insert_date_directory_to_path`). With `original_images/YYYY-MM/` taking 24 of those, filenames are
cut to 70 characters — so two *different* images whose names agree for the first 66 characters land
on one key. Long descriptive names make this ordinary rather than exotic: two chart exports whose
titles differed only in their last words were found sharing a key, both paths exactly 94 characters
long, each having overwritten a different image. Look for stored paths of exactly 94 characters:
that length is the signature, since an untruncated name almost never lands on the cap precisely.
Unlike the paths above, this one destroys content with no duplicate-detection prompt and no copy
operation to hint at what happened.

**Rendition stem truncation.** Renditions have a collision mechanism of their own.
`Image.generate_rendition_file` names a rendition by cutting the original's stem to
`59 - len(output_extension)` characters (`wagtail/images/models.py:889`), so two originals whose
names diverge only past that cut land on one rendition key — and a long filter spec cuts deeper. A
`fill-1200x627-c50` spec with a focal-point key leaves 29 characters of stem, and a `max-1600x1600`
leaves 42; every shared rendition key found in the 2026-08 scans had a stem of exactly that length
for its spec, so the arithmetic is the diagnostic. Distinct photographs whose names agreed up to the
cut were sharing one rendering. The cut is also long enough to remove the de-duplication suffix that
makes two *originals* distinct, so fixing the originals does not by itself keep their renditions
apart. This is contained rather than fixed: `get_available_name` now suffixes a taken rendition key,
so new renditions stay distinct.

Documents collide far more often than images because they land in a flat `documents/` prefix, while
images get a `original_images/YYYY-MM/` date directory. Across the four production clusters the
split was 95 document groups to 16 image groups, plus 22 shared rendition keys on ca-prod alone.

### What is already fixed

Both fixes went to production with 423552039 on 2026-08-24, and `file_overwrite` reads `False` on
all four clusters:

- **`kausal_common/storage/storage_classes.py`** sets `file_overwrite = False` on
  `MediaFilesS3Storage`, restoring filename de-duplication. This closes every collision path above,
  truncation included: the de-duplicating suffix is applied after the name has been trimmed. Beware
  that the value can be overridden per deployment, since `storage_settings_from_s3_url` passes every
  query parameter of `S3_MEDIA_STORAGE_URL` through as a storage option.
- **`src/aplans/media_cleanup.py`** replaces Wagtail's `post_delete_file_cleanup` receivers with
  `guarded_post_delete_file_cleanup`, which refuses to delete a file another row still references.

Neither repairs existing rows. Note also that the guard makes already-shared rows *permanently*
conjoined: nothing will ever delete their shared object, so they stay shared until split explicitly.
That is what `repair_media_files` is for.

Every shared key found in the 2026-08 scans predates that deploy, the ones created in 2026-08
included, so the fixes are doing their job: nothing new has collided since.

## Storage situation

| | fi-prod | de-prod | us-prod | ca-prod |
|---|---|---|---|---|
| Backend | self-hosted MinIO | Hetzner (Ceph RGW) | Hetzner (Ceph RGW) | Hetzner (Ceph RGW) |
| Endpoint | `s3.kausal.tech` | `fsn1.your-objectstorage.com` | `fsn1.your-objectstorage.com` | `fsn1.your-objectstorage.com` |
| Bucket | `watch-media-prod` | `kausal-watch-media-de` | `kausal-watch-media-us` | `kausal-watch-media-ca` |
| Versioning | enabled | enabled | enabled | enabled |
| Lifecycle rules | none | none | none | none |
| App key reads version history | yes | yes, since the policy fix | yes, since the policy fix | yes, since the policy fix |

Every bucket retains full version history from the point versioning was enabled: no lifecycle rule
expires noncurrent versions, so overwritten content and deleted objects are both recoverable within
that window. How far back it reaches is not reported by any API, but the 2026-08 recovery pinned it
down on `watch-media-prod`: every object from 2026 carries a real version id, while the surviving
renditions of images from 2024-06 through 2025-05 all report `VersionId: null` — the marker for an
object written before versioning existed on the bucket. **Versioning was therefore switched on
between roughly 2025-05 and 2026-06, and anything deleted before that is gone.** Every file deleted
after it was recoverable; none deleted before it was.

Each cluster has its own bucket, which matters more than it sounds: the delete guard and the
repair's notion of "every row on this key" are both scoped to one database, so a bucket shared
between clusters would silently defeat both. Verify it before repairing, with
`print(default_storage.bucket_name, default_storage.endpoint_url, default_storage.file_overwrite)`
in a shell on each cluster.

Configuration comes from a single environment variable, `S3_MEDIA_STORAGE_URL`, parsed by
`kausal_common/storage/__init__.py:storage_settings_from_s3_url`:

```
s3://ACCESS_KEY:SECRET@/BUCKET?endpoint_url=https://s3.kausal.tech&addressing_style=virtual
```

The host part is empty; the endpoint arrives as a query parameter.

### The Hetzner buckets needed a policy fix

**These policies are infrastructure as code, so do not edit them by hand.**
`_init_hetzner_media_bucket` in the pulumi repo (`python/kausal_services/projects.py`) calls
`grant_bucket_access` for `kausal-watch-media-{de,us,ca}`, which re-renders the whole document from
`MINIO_BUCKET_ACCESS_POLICY` in `python/common_services/minio.py`. A change made with
`mcli anonymous set-json` therefore survives only until the next `pulumi up`, which will revert it
silently — the tooling then starts failing with `AccessDenied` again with nothing to explain why.
fi-prod's MinIO bucket goes through `create_bucket` and a per-bucket IAM policy rendered from
`MINIO_RW_POLICY` instead, so it needs the equivalent change in that template.

All three Hetzner buckets were provisioned with a policy that granted their application principal
`s3:ListBucket`, `s3:GetBucketLocation` and `s3:DeleteObject` at the bucket level but not
`s3:ListBucketVersions` or `s3:GetBucketVersioning`. Those keys could therefore list objects while
being unable to read version history at all — `ListObjectVersions` returned `AccessDenied`. Only
fi-prod's MinIO allowed it. This was not a de-prod misconfiguration, as first assumed; it is how
Hetzner per-bucket keys come.

That mattered for every shared key, not just the ones needing recovery: `unshare` lists versions
before it does anything else, and every copy it makes pins a `VersionId`, so the repair could not
run at all on those clusters.

The fix, applied to all three on 2026-08-26, adds the two read actions to the existing bucket-level
statement for the app principal; the object-level statement already granted it `s3:*`, which covers
`s3:GetObjectVersion`. Nothing else changed. Two properties of these policies are worth knowing
before editing one again:

- **No policy grants anonymous read.** No statement names `Principal: "*"`, so replacing one of
  these documents cannot take the public site down. Media reaches browsers through presigned URLs
  instead: on fi-prod an unsigned GET of a media object returns 403 while `file.url` hands out a
  signed URL, which makes the `public-read` ACL that `MediaFilesS3Storage.default_acl` sets
  effectively vestigial. `repair_media_files.copy_extra` still passes it on every copy, so a copy is
  no less reachable than its original either way. Verified on fi-prod; the Hetzner policies have the
  same shape, but confirm with an unsigned GET before assuming it.
- **`mcli anonymous set-json` replaces the whole document** rather than merging. Take a backup with
  `mcli anonymous get-json` first, edit the backup, and diff before applying.

The operator credential the tooling accepts (`MEDIA_RECOVERY_S3_*`, see `recovery_client`) is no
longer needed anywhere. It is kept because it costs nothing and covers the case of a bucket whose
policy cannot be changed; note that it is used for *all* S3 calls in a repair run, writes included,
so such a credential needs `CopyObject` and `PutObjectAcl` and not only version reads.

### Tooling notes

- **The AWS CLI is unusable against these endpoints.** Ceph RGW returns errors with an empty
  `<Message></Message>`, and `awscli/customizations/s3errormsg.py` does a substring test on it,
  crashing with `TypeError: argument of type 'NoneType' is not a container or iterable`. The real
  error is only visible under `--debug`, in the logged response body. Use `mcli` or boto3 instead.
- **A directory-like prefix can appear at the bucket root** where a single document object should
  be. One was found on the 2026-08 sweep, matches no upload path the code generates, and was never
  explained. Nothing depended on it, but do not assume such a prefix is a real directory.
- **`mcli` prints non-errors with an `<ERROR>` prefix.** `NoSuchLifecycleConfiguration` from
  `mcli ilm rule ls` means "no lifecycle rules are configured", which is an answer, not a failure.

## Known damage

All four production clusters were scanned on 2026-08-26, renditions not included. 140 problems:
111 shared keys and 29 missing files.

| | shared keys (img / doc) | missing files (img / doc) | `SAME` | `DIFFER` | `UNKNOWN` |
|---|---|---|---|---|---|
| fi-prod | 43 (4 / 39) | 19 (15 / 4) | 40 | 3 | 0 |
| de-prod | 13 (3 / 10) | 6 (3 / 3) | 10 | 3 | 0 |
| us-prod | 51 (6 / 45) | 2 (2 / 0) | 47 | 4 | 0 |
| ca-prod | 4 (3 / 1) | 2 (2 / 0) | 3 | 1 | 0 |

The `SAME`/`DIFFER` columns come from `triage_shared_media`, which compares what the rows on a key
recorded at upload time. **100 of the 111 shared keys lost no content** — they are plan copies that
need nothing but keys of their own, repairable without consulting version history for anything
except the hash check. Only 11 keys, holding 26 rows and 13 distinct contents, are real overwrites.
No row anywhere has a blank `file_hash`, so nothing falls into `UNKNOWN`.

The 29 missing files are mostly recent (all but four are from 2026-05 or later, well inside version
history); the doubtful ones are from 2024-06, 2024-07, 2024-12 and 2025-05.

### Cluster ancestry

fi-prod seeded the other three, so the same damaged rows appear in several clusters *with identical
PKs* — one document group was present in all four. Deduplicated, the 140 problems of the 2026-08
scans were about 115 distinct incidents.

This happened because the seeding path is not plan-scoped: `destructively_trim_db` followed by
`dumpdata` carries every tenant's rows, not just the one being moved, along with shared framework
content and `wagtail_localize` records. `export_plan` is the leak-free route, and any cluster seeded
the other way reproduces this. Repairing the same logical damage in two clusters is the visible
cost; one region's bucket holding another region's customer files is the less visible one.

Which cluster should repair a given row follows from where its plan is actually served, and **the
database cannot answer that**: `PlanDomain` rows were seeded along with everything else, so a
cluster still claims production hostnames that resolve elsewhere. **Check DNS, not `PlanDomain`.**
On that basis fi-prod's copies of four migrated plans were stale, which removed 23 of its 43 shared
keys from the work — all of them `SAME`, so the question gated nothing expensive.

A shared key whose rows are all `NO-PLAN` is a residue signal but not proof. The clearest case found
was a pair whose rows sat in the shared `Common Categories` collection, which belongs to the
common-category framework rather than to any plan, which is how it reached all four clusters.
Nothing referenced either row — checked with `ReferenceIndex` plus a raw column scan, since the
index does not cover `Action`, `Indicator`, the attribute value models or draft revisions. The
cheapest fix for such a pair is to delete *one* row: the key stops being shared, and the delete
guard keeps the file because the survivor still references it, so nothing leaves storage at all.

## The commands

### `check_media_integrity`

*Detects* rows that share a storage key and rows whose file is gone. Read-only, no S3 credentials
beyond the application's own.

- Existence is checked with one `listdir()` per directory rather than one `exists()` per file, so
  the number of storage requests scales with directories rather than with objects. Storages that
  cannot list fall back to per-file checks.
- Renditions are opt-in (`--include-renditions`) because they can be regenerated as long as the
  original survives. They are still worth checking periodically: a shared *rendition* key is the
  same hazard, and now that the delete guard is in place it will never clear itself.
- Exits non-zero via `CommandError`, so it works unmodified as a Kubernetes CronJob alert.

### `triage_shared_media`

*Sorts the shared keys by how much they cost to repair*, from the database alone — no S3 access, no
version history, seconds to run. For each key it compares the `file_hash` and `file_size` its rows
recorded and reports `SAME`, `DIFFER` or `UNKNOWN`, and it attributes every row to a plan via
`Plan.root_collection` and the collection tree.

This is the cheapest thing to run first, and on the production data it moved 90% of the shared keys
into a category that needs no recovery work at all. It answers a different question from
`inventory_media_versions`: what the *rows* claim, rather than what the *bucket* holds. A `SAME`
verdict says the rows agree on their content, not that those bytes are still stored — a group can
agree on a hash whose bytes are nowhere in the history, if versioning began after a sibling had
already overwritten the key. The repair verifies against the bytes regardless.

```
--emit-keys DIR     write same-keys.txt, differ-keys.txt, unknown-keys.txt, residue-keys.txt and
                    (with --include-missing) missing-keys.txt, ready for --keys-file
--include-missing   also attribute rows whose file is gone. Needs `s3:ListBucket`, which the pure
                    database triage does not.
```

Every file is rewritten on each run, empty ones included, so a verdict that no longer has findings
truncates its file rather than leaving an earlier run's keys to be repaired a second time — these
files are fed straight to `--keys-file`, and `repair_media_files` rejects an empty one outright.
`missing-keys.txt` is *deleted* rather than emptied when `--include-missing` was not passed, since an
empty file would claim nothing is missing when the question was never asked.

### `inventory_media_versions`

*Decides what is recoverable*, by joining each affected key's S3 version history against what the
database rows recorded. Read-only — it writes nothing to S3 or the database.

- **`file_hash` is the triage lever.** Wagtail stores a SHA-1 of the contents at upload time
  (`wagtail/utils/file.py:hash_filelike`). Rows in a shared group that agree on their hash lost
  nothing *to each other* and only need separate keys; rows that disagree had content overwritten.
- **A live, unshared key is reported as `intact`, not as missing.** `--keys-file` inspects exactly
  what it is given, so a list reused after a repair still names keys that are now healthy; and in
  discovery mode `listdir` is what nominated the key, which the version listing can contradict.
  Either way the version state decides, so a healthy key is not counted as an incident.
- **The verdict mirrors what the repair would do.** A key counts as recoverable only when every row
  can be traced to a stored version by the same rule `repair_media_files` applies. Agreement among
  the rows is not enough on its own — they can agree on a hash whose bytes are nowhere in the
  history, if versioning began after a sibling had already overwritten the key. A verdict the
  repair would refuse to honour is worse than no verdict.
- **A blank `file_hash` is treated as unknown, never as a match.** The column is populated lazily,
  so older rows have `''`, and treating two blanks as equal would silently classify real data loss
  as harmless.
- **Equal ETags are a free proof that nothing *changed*, not that the content is the right one.**
  If every version of a key shares one ETag the bytes never differed, so one download settles every
  row instead of one per version. But a single-content history is not evidence that the content
  belongs to a given row: where versioning was switched on *after* an overwrite, the only surviving
  content is the sibling's, and the row's recorded hash is the one thing that reveals it. A
  recorded `file_hash` is therefore always checked against the bytes. The converse of the ETag rule
  does not hold either — multipart uploads of identical content differ in ETag when part sizes
  differ — so unequal ETags mean "unknown", not "changed".
- **Unequal ETags never stand in for "the content changed".** A multipart ETag is not a digest of
  the object, so identical bytes stored with different part sizes carry different ETags — readily
  produced when one version was uploaded and another made by a server-side copy. Wherever the
  distinction decides whether a key is recoverable, the bytes are hashed rather than the ETags
  compared; the ETag shortcut is only ever used in the direction that holds, to prove sameness.
- **ETag cannot map a row to a version.** It is an MD5; `file_hash` is a SHA-1. Matching a specific
  row to the version holding its bytes requires downloading, which is what `--verify-hashes` does.
  Without it, versions are matched on recorded `file_size`, which is free but only indicative.
- **`--keys-file` skips discovery**, so the credential in use never needs `s3:ListBucket`.
- **Operator credentials** come from `MEDIA_RECOVERY_S3_ACCESS_KEY_ID` and
  `MEDIA_RECOVERY_S3_SECRET_ACCESS_KEY`. When set, they are used *only* for the versioning API;
  discovery still goes through the application's storage. No cluster needs this any more, since
  every app credential can now read version history. If one ever does, don't pass the secret via
  `kubectl exec env` — it lands in the pod's process arguments, readable by anything that can see
  `/proc`. Use a temporary Kubernetes secret, or run the command locally against the endpoint.

### `repair_media_files`

*Applies the repair.* Dry-run by default; `--execute` is required to write anything.

Shared keys, when all rows recorded the same hash or all versions share one ETag: the lowest-PK row
keeps the key and the others get a copy at a fresh key. When hashes disagree: every version is
hashed, the row matching the *current* bytes keeps the key, and each other row is restored from the
version holding its own recorded hash. If the shared key is currently deleted, the keeper's own
version is also copied back onto it, so the keeper is not left holding a delete marker.

Design decisions:

- **Repair of a shared key is all-or-nothing, in both directions.** Every row must be traceable
  to the bytes it recorded before anything is copied, and the group's rows move together or not at
  all. A partial repair would move some rows while the keeper and the
  unresolvable ones went on sharing a key — harder to reason about than the original problem, and it
  hides the rows that still need attention. The single-content inference is reserved for rows that
  never recorded a hash, where nothing better exists; a row that did record one has it verified
  against the bytes, and the group is reported and skipped if it does not match.
- **Missing files are restored from the version matching the row's `file_hash`**, never the most
  recent one. Where a sibling overwrote the key before being deleted, the newest surviving version
  holds the *sibling's* bytes, so restoring by recency would quietly hand the row a file that was
  never its own. Rows whose hash matches nothing in the history are left for manual review.
- **Restoring copies the matched version forward** rather than deleting the delete marker. This
  preserves history and needs no `s3:DeleteObjectVersion` — the permission worth denying the
  application afterwards (see Follow-ups).
- **`IsLatest` decides what is current, never timestamp order.** `LastModified` has second
  granularity on most S3 implementations, and the uploads that caused this are often seconds apart,
  so a tie can leave the API's newest-first ordering intact and make the *oldest* version look
  current. Version listings are sorted by time for display only.
- **The order within a group is: sibling copies, then the row updates in one transaction, then —
  for a deleted key — the keeper's restore.** Each step is placed so that failing at it leaves the
  prior state intact. Copying before repointing avoids a row pointing at a key that was never
  written, which is precisely the breakage being repaired. One transaction avoids committing half
  a group when a later copy fails. And restoring the shared key *last* matters most: bringing it
  back while the other rows still point at it would serve them the keeper's bytes, which is worse
  than the 404 they had, whereas failing there leaves the keeper merely still missing — the state
  it was already in, and one the integrity check reports.
- **Being shared takes precedence over being missing.** A shared key whose current state is deleted
  is both. `restore_missing` consults only the first row, so sending it there would copy that row's
  bytes onto the key and leave every row still sharing them. `--only missing` therefore skips such
  a key and says so, rather than repairing it wrongly.
- **Rows are updated with `update()`, not `save()`.** The bytes a row *recorded* are unchanged, so
  `file_hash` and `file_size` still hold, and there is no reason to churn revisions. A key change
  alone leaves renditions correct: they are separate objects, and neither
  `find_existing_rendition` — which matches on `(image, filter_spec, focal_point_key)` — nor the
  rendition cache key `[image.id, image.file_hash, filter_cache_key, filter_spec]` involves the path.
- **But restoring an image's *content* leaves its renditions stale**, and nothing here fixes that.
  Where the rows disagreed on their hash, a row's renditions may have been generated while a
  sibling's bytes occupied the shared key, and because `file_hash` is unchanged by the repair —
  it always described this row's own content — the lookup and the cache key both still hit the old
  rendition. Purge renditions for every row in such a group afterwards, keeper included, with
  `image.renditions.all().delete()`; they regenerate on demand. Documents are unaffected.
- **The original key counts as taken when allocating a copy's key**, even when storage says it is
  free. A key with a delete marker on top reads as free, and on a dry run the keeper's content has
  not been restored onto it yet — so asking storage would hand back the very key the row is being
  moved off. Names already allocated in the same run are reserved too, since a dry run writes
  nothing for storage to notice.
- **It refuses to run against a storage with `file_overwrite=True`.** `get_available_name()` would
  return the already-taken key, so every "move" would be a no-op onto the same object, reported as
  success. This is why the branch must be *deployed*, not merely merged, before repairing.

## Procedure

Now that every app credential can read version history, all four clusters follow one sequence, with
the application's own credential throughout.

```fish
# 1. Deploy the de-duplicating storage settings first. The repair refuses to run otherwise,
#    and without them new uploads keep colliding.

# 2. Confirm the current damage
python manage.py check_media_integrity

# 3. Sort it by cost, and get the key files the later steps take
python manage.py triage_shared_media --include-missing --emit-keys /tmp

# 4. Repair the keys that lost nothing. Read the dry run before adding --execute.
python manage.py repair_media_files --keys-file /tmp/same-keys.txt --only shared
python manage.py repair_media_files --keys-file /tmp/same-keys.txt --only shared --execute

# 5. Classify what is recoverable for the rest
python manage.py inventory_media_versions --keys-file /tmp/differ-keys.txt --verify-hashes \
    --json /tmp/inventory.json

# 6. Repair the rest, reading each dry run first
python manage.py repair_media_files --keys-file /tmp/differ-keys.txt --only shared
python manage.py repair_media_files --keys-file /tmp/missing-keys.txt --only missing

# 7. Verify, this time including renditions
python manage.py check_media_integrity --include-renditions
```

Take a database snapshot before the first `--execute`. S3 version history can undo the object
writes; it cannot undo the row updates.

Start on the smallest cluster and with a one-key file, not with a whole cluster: the S3 call paths
have far less test coverage than the decision logic, and a single group's dry run shows the whole
shape of what a real run does.

To scope a run to what an earlier inventory flagged, rather than to a fresh triage:

```fish
jq -r '.[].entries[] | select(.kind != "intact") | .file' /tmp/inventory.json > /tmp/keys.txt
```

**Always pair `--keys-file` with `--only`.** Given an explicit key list, `find_missing` treats every
non-shared key in it as missing rather than listing the bucket, so a stray line in a file fed to a
`missing` run would send a healthy key down the restore path.

Passing a key file to a pod without quoting anything:

```fish
kubectl -n <namespace> exec -i deploy/<deployment> -- \
    sh -c 'cat > /tmp/keys.txt && python manage.py repair_media_files --keys-file /tmp/keys.txt --only shared' \
    < /tmp/local-keys.txt
```

Which cluster repairs which rows depends on where each plan is served; see Cluster ancestry above,
and check DNS rather than `PlanDomain`.

## Follow-ups

- **Deny `s3:DeleteObjectVersion` to the application principal.** Wagtail's delete path only ever
  calls `DeleteObject`, which under versioning creates a recoverable delete marker; it never needs
  to purge a version. An explicit `Deny` makes version history tamper-proof against exactly this
  class of bug, at no functional cost. Note that the Hetzner policies grant the app principal
  `s3:*` on `bucket/*`, so it *can* purge versions today — and an `Allow` that broad can only be
  narrowed by an explicit `Deny` statement. Written but not yet applied: both policy templates in the
  pulumi repo carry it on a `chore/` branch, awaiting a `pulumi preview` and a check that nothing
  prunes the database-backup buckets by deleting versions rather than by lifecycle rule.
- **Run `check_media_integrity` as a CronJob.** It already exits non-zero on findings.
- **Scan renditions** with `--include-renditions` once the originals are repaired, and **delete the
  affected ones rather than repairing them.** Deleting means: select the rendition rows whose `file`
  is shared by more than one row or is missing from storage, and delete those rows, so each
  regenerates from its own original on the next request. Three reasons, the second decisive:
  renditions are derived data, so regeneration is cheap and correct; on a shared rendition key some
  rows serve *another image's* rendering, which re-keying would faithfully preserve and only
  regeneration fixes; and `repair_media_files` does not handle renditions at all, iterating only
  `AplansImage` and `AplansDocument`. Purge after restoring originals, not before, or a rendition
  whose original is still missing cannot regenerate.
- **The Hetzner buckets have no independent backup.** Versioning protects against application-level
  mistakes, not against bucket loss.
- **Reconsider the developer credential's read access to production media.**
  `_init_hetzner_media_bucket` grants a development principal `readonly` on all three regional
  buckets, so one credential can read every region's media. That is deliberate and lives in IaC
  rather than being an accident, but it deserves a decision rather than an assumption.
- **Renditions are a last-resort recovery source** for images with no surviving version, and the one
  that actually paid off: on fi-prod the four images deleted before versioning existed still had
  renditions, including a `max-1600x1600` for a 2048×1365 original. Willow re-encodes, so a rendition
  is not byte-identical, JPEGs take a second lossy pass, and EXIF is gone — acceptable for display,
  not a true restore. Probe by S3 prefix (`images/<image created month>/<stem>`) rather than through
  the rendition rows, which may have been purged; under versioning a deleted rendition is still there
  beneath its delete marker. Replace the original through the Wagtail admin so `file_hash`,
  `file_size` and the dimensions are recomputed, then purge that image's renditions. Note the
  substitution somewhere durable: afterwards nothing in the database records that the image was lost.

## Testing

The classification and repair decision logic is covered by unit tests, including keeper selection,
restore-from-own-version, unresolvable groups, delete-marker restore, dry-run inertness, and the
`file_overwrite` guard. `triage_shared_media` needs no S3 at all, so its verdicts, plan attribution
and key files are covered directly. The S3 call paths themselves — `copy_object`, ACL handling,
pagination — are exercised only against a fake client, which has been wrong about real S3 twice
(multipart ETags, delete-marker visibility). Treat the first run on a given backend as the real smoke
test, on a one-key run rather than a whole cluster.

First live results, 2026-08-26 and 2026-08-27, run on all four clusters. Every path is now proven
against real storage on both backends:

- **Shared keys:** all 111 split, across 137 rows. No group was ever left for review, and every
  cluster's problem count landed on the number predicted beforehand — the strongest evidence that
  the planning and the execution agree.
- **Missing files:** 17 restored from noncurrent versions sitting beneath delete markers, each
  matched by hash rather than by recency, and each verified afterwards by re-hashing the restored
  bytes.
- **Renditions:** every shared rendition key purged and regenerated.
- One cluster reached zero findings including renditions; the rest are held open only by files
  deleted before versioning existed.

Copies came back byte-identical by ETag *and* SHA-1 on both backends, and `copy_object` preserved
`ContentType`. The latter is worth keeping in mind if the copy call is ever edited —
`MetadataDirective` defaults to `COPY`, and switching it to `REPLACE` would turn every copied PDF
into `binary/octet-stream`.

The allocated names can look strange, and correctly so. Django 6 computes the extension as
`"".join(PurePath(name).suffixes)`, i.e. *every* suffix, so the random component lands before the
whole chain — a name containing an early dot has the suffix inserted at that dot rather than before
the real extension, which can leave most of the name looking like an extension. The real extension
always survives, so content types and Wagtail's filename handling are unaffected; only the download
filename looks odd. The same applies to `max_length`: a name at the 100-character cap has its root
trimmed further to make room for the suffix.
