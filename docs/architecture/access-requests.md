# Access Requests

How a visitor who cannot read an internal plan asks for access, and how plan admins decide.

## Where it fits

An internal plan shows anonymous visitors a sign-in page (`SIGN_IN_REQUIRED`, see
[Plan Visibility](plan-visibility.md)). When the plan has `PlanFeatures.enable_access_requests`
on, that page can offer an access request instead of a dead end. The restricted plan type exposes
`accessRequestsEnabled` and `accessRequestEligibilityText` so the page can decide what to show.

Approving grants the **public site only**: a `PlanPublicSiteViewer` row, never admin rights.

Signing in itself is not part of this feature, but the approval email lets a new visitor set their
password without typing their address again (see [Setting a password](#setting-a-password)).

## The request

`AccessRequest` holds one attempt: plan, email, optional names, status (`pending`, `approved`,
`rejected`), and who decided when. At most one request per address and plan is pending. A
rejected visitor who asks again gets a new row, so the rejection stays on record and the admin
list can mark the new one "requested again" with the date of that rejection
(`AccessRequestQuerySet.with_previous_rejection`).

The public UI files requests with the `requestPlanAccess` mutation, in the plan context of the
request (`@context(input: {hostname})`). The address is not verified, so:

- The mutation answers `ok: true` whether a request was recorded, was already waiting, or was not
  needed because the address can already read the plan. Only refusals carry a code:
  `ACCESS_REQUESTS_DISABLED`, `INVALID_EMAIL`, `INVALID_NAME`, `RATE_LIMITED`, `TOO_MANY_PENDING`.
- Filing a request sends the visitor nothing. Their first email is the decision.
- Requests are rate limited per client IP, and a plan takes no more once too many are waiting.

## Deciding

Plan admins decide on the admin home, where a panel lists the waiting requests oldest first.
Approving acts at once; rejecting is confirmed in a dialog, since it emails the visitor.

All state changes live in `access_requests.services`:

- `approve_access_request` reuses a person with the same address or creates one in the plan's
  organization (which also creates their user), and adds the viewer row. Someone who already has
  admin rights in the plan gets no viewer row: the person form reads such a row as
  "public site only" and would hide their admin rights.
- Both decisions lock the row and refuse a request another admin already decided.

The approve and reject views are not atomic as a whole. The decision commits first, then the
decision email is sent, so the admin learns in the same response if the email could not be sent;
the decision stands either way.

## Emails

| email | to | when | look |
|---|---|---|---|
| approved / not approved | the visitor | right after the decision | the plan's theme, in the plan's language |
| new access requests | the plan's admins | the plan's daily notification run | the admin interface's look |

The visitor emails (`access_requests.emails`) are plan-themed when the plan has a notification base
template and plain text otherwise. The "not approved" email repeats the plan's eligibility text and,
when set, its contact address (`Plan.access_request_eligibility_text`,
`Plan.access_request_contact_email`).

The digest is the `ACCESS_REQUESTS_RECEIVED` notification type. Each request is announced once,
through `SentNotification`, while the total still waiting is repeated each time. Its template is
seeded when a plan switches access requests on. It is the one notification rendered with the admin
theme (`Notification.uses_plan_theme = False`) rather than the plan's, because it is about the admin
interface.

## Setting a password

The approval email carries a one-time link to set a password
(`access_requests.emails.make_set_password_url`), but only when the visitor needs one
(`may_set_password`):

- not for an SSO user, who has no usable password and signs in through their organisation;
- not for someone who has signed in before, who has a password already and did not ask for a
  reset;
- only for an approved request whose plan has a site URL.

The link is Django's password reset token, with the access request's pk in the path, served by
`access_requests.views.SetPasswordView`, a subclass of Django's `PasswordResetConfirmView` (not
Wagtail's: the page is for visitors, and it is in the plan's language). It works once, and expires
after `PASSWORD_RESET_TIMEOUT`. A link that no longer matches the request, because the request was
decided otherwise or belongs to someone else, gets the same "invalid link" page as a bad token.

Setting the password signs the visitor in on the backend and redirects them to
`<plan view URL>/access-approved`. The public UI provides that page; because the backend session
exists, its OAuth sign-in goes through without asking for the password again. Once the link has
expired, the visitor uses "forgot password" on the sign-in page.
