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

### The two code paths that caused it

**Chooser re-uploads.** Uploading a file whose name already exists writes over the existing object.
Wagtail then notices the contents match and offers to reuse the existing image; confirming that
deletes the row it just created — along with the file both rows point at.

**Plan copying.** `copying/main.py:copy_collection_with_contents` duplicates a collection's images
and documents with `file.save(filename, content_file)`. With `file_overwrite=True`, that "copy"
wrote straight over the source object and left both rows on one key. This is the larger cause by
volume, and it is recognisable in the data: the affected PKs come in contiguous blocks mapping onto
scattered older PKs, rather than in same-session pairs.

Documents collide far more often than images because they land in a flat `documents/` prefix, while
images get a `original_images/YYYY-MM/` date directory (`images/models.py:insert_date_directory_to_path`).
On the fi-prod scan the split was 39 document groups to 4 image groups.

### What is already fixed

Both fixes are on `fix/shared-media-file-deletion`:

- **`kausal_common/storage/storage_classes.py`** sets `file_overwrite = False` on
  `MediaFilesS3Storage`, restoring filename de-duplication. This fixes both code paths above,
  including plan copying.
- **`aplans/media_cleanup.py`** replaces Wagtail's `post_delete_file_cleanup` receivers with
  `guarded_post_delete_file_cleanup`, which refuses to delete a file another row still references.

Neither repairs existing rows. Note also that the guard makes already-shared rows *permanently*
conjoined: nothing will ever delete their shared object, so they stay shared until split explicitly.
That is what `repair_media_files` is for.

## Storage situation

| | fi-prod | de-prod |
|---|---|---|
| Backend | self-hosted MinIO | Hetzner Object Storage (Ceph RGW) |
| Endpoint | `https://s3.kausal.tech` | `https://fsn1.your-objectstorage.com` |
| Bucket | `watch-media-prod` | `kausal-watch-media-de` |
| Versioning | enabled | enabled |
| Lifecycle rules | none | none |
| App key reads version history | yes | **no** |

Both buckets retain full version history: versioning is on and no lifecycle rule expires noncurrent
versions, so overwritten content and deleted objects are both recoverable. How far back that reaches
depends on when versioning was switched on, which no API reports — the inventory command answers it
empirically per key.

Configuration comes from a single environment variable, `S3_MEDIA_STORAGE_URL`, parsed by
`kausal_common/storage/__init__.py:storage_settings_from_s3_url`:

```
s3://ACCESS_KEY:SECRET@/BUCKET?endpoint_url=https://s3.kausal.tech&addressing_style=virtual
```

The host part is empty; the endpoint arrives as a query parameter.

### de-prod needs a second credential

The bucket policy on `kausal-watch-media-de` grants the application principal `s3:ListBucket`,
`s3:GetBucketLocation` and `s3:DeleteObject` at the bucket level — but not `s3:ListBucketVersions`
or `s3:GetBucketVersioning`. The app key can therefore list objects but cannot read version history
at all.

A credential from the project that *owns* the bucket can read version history (scoped to a known
prefix) but cannot `ListBucket`. So on de-prod the two capabilities live in different keys, which is
why the tooling takes an operator credential separately from the application's own.

### Tooling notes

- **The AWS CLI is unusable against these endpoints.** Ceph RGW returns errors with an empty
  `<Message></Message>`, and `awscli/customizations/s3errormsg.py` does a substring test on it,
  crashing with `TypeError: argument of type 'NoneType' is not a container or iterable`. The real
  error is only visible under `--debug`, in the logged response body. Use `mcli` or boto3 instead.
- **`mcli` prints non-errors with an `<ERROR>` prefix.** `NoSuchLifecycleConfiguration` from
  `mcli ilm rule ls` means "no lifecycle rules are configured", which is an answer, not a failure.

## Known damage

The fi-prod scan on 2026-08-18 (renditions not included) found 62 problems: 4 shared image keys,
15 missing images, 39 shared document keys, 4 missing documents. de-prod has not been scanned yet;
the plan-copying path ran there too, so expect a similar document-heavy pattern.

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

### `inventory_media_versions`

*Decides what is recoverable*, by joining each affected key's S3 version history against what the
database rows recorded. Read-only — it writes nothing to S3 or the database.

- **`file_hash` is the triage lever.** Wagtail stores a SHA-1 of the contents at upload time
  (`wagtail/utils/file.py:hash_filelike`). Rows in a shared group that agree on their hash lost
  nothing *to each other* and only need separate keys; rows that disagree had content overwritten.
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
  discovery still goes through the application's storage. This matches de-prod exactly.

### `repair_media_files`

*Applies the repair.* Dry-run by default; `--execute` is required to write anything.

Shared keys, when all rows recorded the same hash or all versions share one ETag: the lowest-PK row
keeps the key and the others get a copy at a fresh key. When hashes disagree: every version is
hashed, the row matching the *current* bytes keeps the key, and each other row is restored from the
version holding its own recorded hash. If the shared key is currently deleted, the keeper's own
version is also copied back onto it, so the keeper is not left holding a delete marker.

Design decisions:

- **Repair of a shared key is all-or-nothing.** Every row must be traceable to the bytes it
  recorded before anything is copied. A partial repair would move some rows while the keeper and the
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
- **The S3 copy happens before the database update.** A failure between the two leaves an
  unreferenced object, which is harmless; the reverse would leave a row pointing at a key that was
  never written, which is precisely the breakage being repaired.
- **Rows are updated with `update()`, not `save()`.** The bytes are unchanged, so `file_hash` and
  `file_size` still hold, and there is no reason to churn revisions or re-render renditions.
  Renditions are unaffected by an original's key changing: they are separate objects, and Wagtail's
  rendition cache key uses `file_hash`, not the path.
- **The original key counts as taken when allocating a copy's key**, even when storage says it is
  free. A key with a delete marker on top reads as free, and on a dry run the keeper's content has
  not been restored onto it yet — so asking storage would hand back the very key the row is being
  moved off. Names already allocated in the same run are reserved too, since a dry run writes
  nothing for storage to notice.
- **It refuses to run against a storage with `file_overwrite=True`.** `get_available_name()` would
  return the already-taken key, so every "move" would be a no-op onto the same object, reported as
  success. This is why the branch must be *deployed*, not merely merged, before repairing.

## Procedure

### fi-prod

The application's own credential can do everything here.

```fish
# 1. Deploy fix/shared-media-file-deletion first. The repair refuses to run otherwise,
#    and without it new uploads keep colliding.

# 2. Confirm the current damage
python manage.py check_media_integrity

# 3. Classify what is recoverable
python manage.py inventory_media_versions --json /tmp/fi-inventory.json

# 4. Review the plan — read this carefully, it is the last checkpoint
python manage.py repair_media_files

# 5. Apply, shared keys first
python manage.py repair_media_files --execute --only shared
python manage.py repair_media_files --execute --only missing

# 6. Verify, this time including renditions
python manage.py check_media_integrity --include-renditions
```

Take a database snapshot before step 5. S3 version history can undo the object writes; it cannot
undo the row updates.

### de-prod

Same sequence, with three differences.

**Discovery and version reads use different credentials.** Run `check_media_integrity` with the
application's credential, then feed the affected keys to the other two commands with the operator
credential:

```fish
python manage.py check_media_integrity                       # app credential
python manage.py inventory_media_versions --keys-file /tmp/keys.txt --json /tmp/de-inventory.json
python manage.py repair_media_files --keys-file /tmp/keys.txt
```

with `MEDIA_RECOVERY_S3_ACCESS_KEY_ID` and `MEDIA_RECOVERY_S3_SECRET_ACCESS_KEY` set to the
owner-project key.

**Do not pass the operator secret via `kubectl exec env`** — it lands in the pod's process arguments
and is readable by anything that can see `/proc`. Use a temporary Kubernetes secret, or run the
command locally against the endpoint.

**Verify the operator key can write before running the repair.** It is confirmed to read version
history, but its ability to `CopyObject` into the bucket has not been established, and the repair
uses one credential for both. Test with a throwaway key first. The cleaner long-term fix is to add
`s3:ListBucketVersions` and `s3:GetObjectVersion` to the application principal in the bucket policy,
after which de-prod needs no operator credential at all and its procedure becomes identical to
fi-prod's.

Editing that policy carries real risk: `mcli anonymous set-json` **replaces** the whole document
rather than merging, and the bucket serves public media for a live site. Back it up with
`mcli anonymous get-json` first and edit the backup.

## Follow-ups

- **Deny `s3:DeleteObjectVersion` to the application principal.** Wagtail's delete path only ever
  calls `DeleteObject`, which under versioning creates a recoverable delete marker; it never needs
  to purge a version. An explicit `Deny` makes version history tamper-proof against exactly this
  class of bug, at no functional cost.
- **Run `check_media_integrity` as a CronJob.** It already exits non-zero on findings.
- **Scan renditions** with `--include-renditions` once the originals are repaired.
- **de-prod has no independent backup** of its media bucket. Versioning protects against
  application-level mistakes, not against bucket loss.
- **Original-size renditions are a last-resort recovery source** for images with no surviving
  version. Willow re-encodes, so a rendition is not byte-identical, JPEGs take a second lossy pass,
  and EXIF is gone — acceptable for display, not a true restore.

## Testing

The classification and repair decision logic is covered by unit tests, including keeper selection,
restore-from-own-version, unresolvable groups, delete-marker restore, dry-run inertness, and the
`file_overwrite` guard. The S3 call paths themselves — `copy_object`, ACL handling, pagination — are
exercised only against a fake client. Treat the first production dry run as the real smoke test.
