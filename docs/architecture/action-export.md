# Action Export from the Public UI

## Overview

The public UI's action dashboard has an export menu. Its links go to
`/report_export/<plan_identifier>/`, which the `actionReportExportViewUrl` field on the plan
returns. The view is `export_report_view` in `src/reports/views.py`. It builds a transient,
unsaved `ReportType`, then produces an incomplete `Report` for it and runs the regular report
spreadsheet exporter (`ExcelReport`) on that report.

Query parameters:

| Parameter | Values | Meaning |
|-----------|--------|---------|
| `format`  | `xlsx` (default), `csv` | Output format |
| `actions` | comma-separated action ids | Restrict the export to these actions |
| `fields`  | absent, or `all` | Which columns to export (see below) |

`ExcelReport` filters rows the same way in both modes. Actions and child plans the requester
may not see are left out, and so are indicators and task assignees they may not see.

## Visible columns (default)

`ReportType.generate_for_plan_dashboard` takes the columns from the `dashboard_columns` of the
plan's action list page. That is the table the visitor was looking at. Attribute columns are
kept only for attribute types visible to the public, whoever is asking.

## All columns (`fields=all`)

`ReportType.generate_for_plan_all_fields` includes every block of `ReportFieldBlock`, plus:

- one category column per category type of the plan that is usable for actions;
- one attribute column per action attribute type the requester may see for **every** action.

The requester must be authenticated and pass `User.can_access_public_site(plan)`, which covers
plan admins, contact persons and public-site viewers. Anyone else gets 403. The export is not
downgraded to the visible columns, because the requester asked for columns they would not get.

Attribute types are filtered by `instances_visible_for`:

| Level | Included for |
|-------|--------------|
| `public`, `authenticated` | everyone allowed to use `fields=all` |
| `contact_persons`, `moderators`, `plan_admins` | plan admins only |

Contact-person and moderator visibility depends on the action. A contact person may see a value
on their own action but not on the others. The exporter builds whole columns and cannot blank
single cells, so those columns are only included for plan admins, who may see them on every
action.

## Authentication

The view accepts two kinds of credentials.

**Bearer token (the public UI).** The UI does not link to this URL directly. Its export menu posts
to a route on the UI's own server, and that route calls this view with
`Authorization: Bearer <ID token>`. This is the same token the UI sends to GraphQL, and it is
checked by the same `authenticate_from_authorization_header`. A token that doesn't validate, or
that belongs to an inactive user, gets 401. A valid token decides the user even when the request
also carries a session cookie for somebody else.

**Session cookie (fallback).** Without an `Authorization` header, `request.user` comes from the
Django session. This covers someone opening the URL on the admin host while logged in there. The
public UI can't rely on it:

- The UI's login sets the session cookie on the admin host only. The export URL the API returns
  is on the API host, so the browser never sends the cookie with it.
- A password login keeps the session only until the browser closes. The UI's session outlives it.
- Signing out of the UI leaves the backend session alive. Logging out of the admin does not sign
  the user out of the UI.
- Impersonation, or an admin login as another user in the same browser, makes the session a
  different user from the one the UI shows.
- Deactivating a user or changing their password ends the session. The UI's token keeps working
  until it expires.
