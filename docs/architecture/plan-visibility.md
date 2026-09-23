# Plan Visibility

Who may read a plan, and what each of its hostnames serves.

## Two independent questions

Visibility used to be decided by four knobs in four places, re-derived in three code paths that
could disagree — and did. A plan with no publication date became publicly readable on its
production domain while that same domain reported itself unpublished, so a customer's site
served a plan nobody had published.

The model now separates the two questions that were tangled together, and answers each in one
place.

**`Plan.visibility`** — `internal` or `public`, defaulting to `internal` — is a hard
authorization gate on the plan's data. It applies wherever a plan is read: GraphQL by hostname,
GraphQL by identifier, REST, search, exports. Nothing widens it.

- `internal` — only signed-in users who have been granted access to this plan can read it.
  Being signed in is not enough on its own: `can_access_public_site` requires admin rights on
  the plan or an explicit public-site-viewer grant, so a user signed in to another customer's
  admin gets nothing.
- `public` — anyone can read it, without signing in.

**`Plan.published_at`** says whether the production surface has been switched on. It says
nothing about who may read the plan. A plan can be readable but not yet launched, which is the
normal state of a site being prepared.

## The four states

| visibility | launched | production domain | wildcard / preview host |
|---|---|---|---|
| internal | no | unavailable page | sign-in page |
| public | no | unavailable page | site |
| internal | yes | **sign-in page** → the site once signed in | sign-in page |
| public | yes | site | site |

No combination is forbidden, so nothing has to be enforced. The third row is the plan that stays
internal after launch — a site every visitor must sign in to. It is rare, but it is a state the
model expresses rather than an exception bolted on.

## One answer per hostname

`PlanDomain.status_for_user` folds both halves back together into the single value the public UI
needs, naming the page to render:

- `AVAILABLE` — serve the site
- `SIGN_IN_REQUIRED` — serve a sign-in page, because signing in would reveal the site to this
  viewer
- `UNAVAILABLE` — serve a placeholder, because nothing here will reveal anything yet

`PlanInterface.resolve_type` returns the plan's body exactly when that status is `AVAILABLE`, so
the two signals are one derivation with two consumers and cannot drift apart. Two derivations of
the same question disagreeing is the precise mechanism of the original bug, which is why the
frontend gates on this one value rather than combining it with anything else.

Its two halves:

- **Has this hostname launched?** A preview surface always has — it exists to be looked at
  before launch. A production surface has once the plan's publication date has passed.
  `PlanDomain.publication_status_override` forces this for a single hostname, and only this; it
  never affects who may read the plan.
- **May this viewer read the plan?** `Plan.visibility`, plus any access the viewer has been
  granted.

A viewer is served the site only when both say yes, and is offered a way in only when signing in
could change the answer — so a hostname serving nothing does not offer a sign-in button that
cannot reveal anything.

## Which hostnames are previews

A `PlanDomain` row tagged `deployment_environment` preview or development is a preview surface.
So is a hostname with no row at all, synthesised from a wildcard base — those exist precisely to
preview a plan, and are constructed as preview surfaces so nothing needs to know they were
synthesised.

A row with no deployment environment set counts as production. Many older rows have none, and
treating them as production is the cautious reading: it withholds rather than reveals.

## Launching does not gate the data

`plan(id:)`, REST and search carry no hostname, so they follow `visibility` alone. A `public`
plan is readable through them before it launches — its data was already public; what has not
happened is the launch of its site. Only the hostname path returns no plan body when that
hostname is not serving, which is what it would have rendered anyway.

This is the orthogonality the model rests on: the launch gate governs a *surface*, not the API.

## Vocabulary

The two axes deliberately share no word, in any language, because the admin shows both:

| axis | reads as |
|---|---|
| who may read the plan (`visibility`) | **Public** · **Internal** |
| has the site launched (`live_state`) | **Live** · **Not live** · **Scheduled** |

A plan that has launched but stayed internal therefore reads as *Live · Internal*, which
describes itself. "Live" is this axis's word throughout the model — `Plan.is_live()`, the
`live()` queryset — while "publish" remains the verb, because it is the word customers use.

These labels are not superuser-only: the sidebar badge renders on every admin page for every
user with an active plan, and the plan list is reachable by contact persons. Their audience is
someone who has never published anything and cannot see the `visibility` field at all.
