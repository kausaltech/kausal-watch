# Paths target node ID and category pages

This note summarizes how **`paths_target_node_id`** (GraphQL clients often expose it as **`pathsTargetNodeId`**) relates to Wagtail pages, what we verified in **Kausal Watch** (this repo), and why changing it in the admin may not affect the public site.

## Problem statement

Editors want a **single Kausal Paths target node ID** for impacts across **category / strategy pages** (two-level category types such as “Handlungsfelder” and “Strategien”). After adding **Category level list** on the appropriate **Category type page**, publishing, and testing in an incognito window, **the public behaviour did not change**.

## What the field is

- Defined on the **`CategoryTypeLevelListBlock`** Wagtail struct block in `src/actions/blocks/category_list.py`.
- Optional string (`max_length=200`), editor label **“Kausal Paths target node ID”**.
- Help text states that if it is not set, **“the default outcome node will be used.”** That default is **not** implemented as a separate plan-level setting in this Django codebase; it is either **frontend (Watch UI) behaviour** and/or **Kausal Paths** instance behaviour.

## Where the block exists in the page model

| Page type | Model | `body` includes **Category level list**? |
|-----------|--------|----------------------------------------|
| Content page | `StaticPage` | Yes |
| Category type page | `CategoryTypePage` (subclasses `StaticPage`) | Yes (same `body` as `StaticPage`) |
| Category page | `CategoryPage` | **No** — different block set; has **Category list**, not **Category level list** |
| Front page | `PlanRootPage` | No (other blocks only) |

Relevant code: `src/pages/models.py` — `StaticPage.body` includes `('category_level_list', CategoryTypeLevelListBlock())`; `CategoryPage.body` does not.

## Where to edit in Wagtail admin

- **Category level list** (and thus **Paths target node ID**) appears under **Body** on **Content page** and **Category type page** only.
- It does **not** appear on **Category page** (e.g. a strategy page like “Strom”), by design.
- An **empty Body** on a category type page only means no blocks were added yet; use **Add block → Category level list** and fill the fields, then **Publish**.

**Category type pages** are real pages (`CategoryTypePage`). They are often **created automatically** when a `CategoryType` has **“Synchronize with pages”** enabled (`src/actions/models/category.py` — `synchronize_pages`). They live under the plan root and are titled from the category type name. They can also be created manually if your permissions allow **Add page → Category type page**.

## Caching (Kausal Watch backend)

- GraphQL execution caching (e.g. Strawberry `WatchExecutionCacheExtension` in `src/aplans/schema_context.py`) keys off **`plan.cache_invalidated_at`**.
- Successful **POST** requests from **`/admin/`** or **`/wadmin/`** trigger **`plan.invalidate_cache()`** on commit (`src/aplans/middleware.py`), which bumps that timestamp and **invalidates** those cache entries for subsequent requests.

So after **Publish** from Wagtail, **stale server-side GraphQL cache** is an unlikely explanation if the UI actually requested updated fields.

## What we concluded about “nothing changed”

After **publish** (not draft) and **incognito** testing:

1. **Draft vs live** and **simple browser cache** were ruled out as the cause.
2. The **backend** stores and exposes **`paths_target_node_id`** on stream blocks that include **Category level list** on **`StaticPage` / `CategoryTypePage`** `body` (Grapple `GraphQLString('paths_target_node_id', ...)` on the block).
3. **Category pages** never carry that block; strategy URLs are typically **`CategoryPage`** instances.
4. The **citizen-facing app** is **[kausal-watch-ui](https://github.com/kausaltech/kausal-watch-ui)** (separate from this repository). Whether impacts use **`pathsTargetNodeId`** from an **ancestor category type page** (or at all) for category/strategy routes is determined **there**, not in this repo.

**Working hypothesis:** the API may return the configured value on the category type page’s `body`, but the **Watch UI does not read or pass that value** for the category/strategy views you tested—so CMS changes look like they “do nothing.”

## How to verify the API

Inspect GraphQL responses (browser Network tab on the public site, or GraphiQL/Voyager on `/v1/graphql/`) for the **category type page** you edited: resolve **`body`** and the union type for **Category level list**, and check for **`paths_target_node_id`** / **`pathsTargetNodeId`**.

- If the value **is** present → focus on **kausal-watch-ui** (or deployment-specific UI) to use it for impacts on category pages.
- If it **is not** present → check locale, published revision, correct page, and query shape.

## Suggested next steps

1. Confirm in GraphQL that **`paths_target_node_id`** is returned on the intended **Category type page** `body`.
2. In **kausal-watch-ui**, trace how Paths impacts are requested for **Category page** routes and whether **`pathsTargetNodeId`** from the parent **Category type page** (or another source) is passed through.
3. If product intent is a **plan-wide** default without using streamfields, that would require **new** backend and/or UI design (this repo does not define a dedicated “default outcome node” field for plans beyond block-level help text).

## Code references (this repo)

- Block definition: `src/actions/blocks/category_list.py` — `CategoryTypeLevelListBlock`, `paths_target_node_id`.
- StreamField placement: `src/pages/models.py` — `StaticPage.body` includes `category_level_list`; `CategoryPage.body` does not.
- Category type page model: `src/pages/models.py` — `CategoryTypePage`.
- Auto page creation: `src/actions/models/category.py` — `CategoryType.synchronize_pages()`.

---

*This document was written to capture investigation context; update it if behaviour or UI wiring changes.*
