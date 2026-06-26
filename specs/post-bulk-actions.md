# Spec: Post Bulk Actions — Existing Views Enhancement

**Status:** Draft for review  
**Date:** 2026-06-25  
**Author:** Hermes Agent  
**Target:** BrightBean Studio (composer + approvals)

---

## 1. Problem Statement

Today, every post action is single-target: click a row to edit, click Approve/Reject per row, no way to delete multiple drafts at once. The approval queue already has a bulk action bar but it uses a floating pattern that doesn't match the rest of the UI.

**Goal:** A minimal, WordPress-style enhancement to existing post list views — add a checkbox column before each row and a header bar with a bulk actions dropdown. No new pages, no new tabs, no floating bars.

---

## 2. Scope

### In scope

- **Checkbox column** inserted as the first column in existing post list tables
- **Header bar** with a "Bulk Actions" dropdown (left-aligned, above the column headers) + an "Apply" button
- Actions: **Delete**, **Send to Queue**, **Publish**, **Reject** (where applicable per view)
- A **delete confirmation dialog** (native `<dialog>`)
- **Selection resets** after action completes or view changes
- **Variable pagination** with rows-per-page control (25 / 50 / 100) on post list views

### Out of scope

- New consolidated "All Posts" page — use the existing Drafts List, Approval Queue, and Calendar views
- Floating action bar — use the WordPress-style header dropdown instead
- Selection persistence across views — clears on action or navigation
- Pagination or variable rows-per-page — existing pagination is unchanged

---

## 3. Views to Enhance

| Existing View | Template | Bulk Actions to Add |
|---|---|---|
| Drafts List | `composer/drafts_list.html` | Delete, Send to Queue |
| Approval Queue | `approvals/queue.html` | Delete, Approve All, Reject All (already exists — replace floating bar with header dropdown) |
| Calendar | `calendar/...` | Delete |

Each view gets the same checkbox + header bar structure adapted to its context.

---

## 4. UI Change

### Before (Drafts List — current)

```
┌────────────────────────────────────────────────────────────────┐
│  Drafts                                    [+ New Post]        │
│  12 drafts                                                      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Most cafés don't need more ideas — they need better...   │   │
│  │ 3 hours ago • by Alex                       [MA][BL]     │   │
│  ├──────────────────────────────────────────────────────────┤   │
│  │ We cut our milk waste by 40% last quarter...             │   │
│  │ Yesterday • by Alex                           [LI]       │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### After (Drafts List — enhanced)

```
┌────────────────────────────────────────────────────────────────┐
│  Drafts                                    [+ New Post]        │
│  12 drafts                                                      │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ [Bulk Actions ▼]  [Apply]                                │   │
│  ├────┬─────────────────────────────────────────────────────┤   │
│  │ ☐  │ Most cafés don't need more ideas — they need...    │   │
│  │ ☐  │ We cut our milk waste by 40% last quarter...       │   │
│  │ ☐  │ Fresh coffee at home, delivered to your door...     │   │
│  └────┴─────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### Key differences from the (rejected) previous spec

| Old approach | This approach |
|---|---|
| New "All Posts" page with tabs | Enhance existing Drafts, Queue, Calendar views |
| Floating action bar at bottom | Header dropdown above columns (WordPress style) |
| Complex pagination controls | Keep existing pagination as-is |
| Post CRUD with full table columns | Just add checkbox + header actions |
| Column headers (Status, Platform, Author) | Keep existing row layout, prefix with checkbox |

---

## 5. Implementation

### 5.1 Template changes

**`composer/drafts_list.html`:** 
- Wrap the list in an Alpine `x-data="{ selectedPosts: [] }"` scope
- Add `<input type="checkbox" x-model="selectedPosts" value="{{ draft.id }}">` before each draft row's content
- Add a header row above the list with bulk actions dropdown + Apply button
- Add a hidden `<form>` for HTMX bulk POST
- Add a `<dialog>` for delete confirmation

**`approvals/queue.html`:**
- Already has checkboxes and `selectedPosts` array — remove the floating bar
- Add the header bar dropdown (Delete, Approve All, Reject All) where the filter tabs end
- Keep the existing `<form hx-post="...bulk_action..."` but remove floating bar markup

**Calendar partials:**
- If the calendar has a post list, add checkbox + bulk delete header

### 5.2 View changes

**New view — `composer:posts_bulk_action`:**
```python
@login_required
@require_POST
def posts_bulk_action(request, workspace_id):
    workspace = _get_workspace(request, workspace_id)
    post_ids = request.POST.getlist("post_ids")
    action = request.POST["action"]

    match action:
        case "delete":
            Post.objects.filter(id__in=post_ids, workspace=workspace).delete()
        case "send_to_queue":
            # Transition all PlatformPost children from draft → pending_review
            PlatformPost.objects.filter(
                post_id__in=post_ids, post__workspace=workspace, status="draft"
            ).update(status="pending_review")
        case "publish":
            # Transition approved/scheduled → publishing
            PlatformPost.objects.filter(
                post_id__in=post_ids, post__workspace=workspace,
                status__in=["approved", "scheduled"]
            ).update(status="publishing")
        case "reject":
            PlatformPost.objects.filter(
                post_id__in=post_ids, post__workspace=workspace,
                status__in=["pending_review", "pending_client"]
            ).update(status="rejected")

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "bulkActionComplete"},
    )
```

**Existing `approvals:bulk_action`:** Keep as-is. The header dropdown replaces the floating bar but the backend is unchanged.

### 5.3 URL changes

```python
# composer/urls.py
path("posts/bulk-action/", views.posts_bulk_action, name="posts_bulk_action"),
```

### 5.4 Pagination

Each enhanced view gets a **rows-per-page control** below the post list, matching the WordPress pattern:

```
┌──────────────────────────────────────────────────────────────┐
│  Rows per page: [25 ▼]        1–25 of 87    ‹  ›            │
└──────────────────────────────────────────────────────────────┘
```

- Options: **25** (default), **50**, **100**
- Uses Django's `Paginator` in the view
- State is URL-parameter-based (`?per_page=50&page=2`) — no Alpine state needed
- Works alongside existing filter parameters (`?status=...&per_page=25`)
- Applied per-view: `composer:posts_list` needs pagination added; `approvals:queue` already uses pagination or can be extended

Views are updated to pass a `Paginator`-wrapped queryset and render the control at the bottom of the list template.

### 5.5 Alpine state

```html
<div x-data="{ selectedPosts: [] }">
```

- `selectedPosts` array holds post IDs from checked checkboxes
- Header dropdown defaults to disabled placeholder when `selectedPosts` is empty
- Apply button is disabled (greyed out, `cursor-not-allowed`) when no posts selected
- Selected count shown: "2 selected" appears next to the Apply button

---

## 6. Actions Per View

| View | Delete | Send to Queue | Publish | Reject | Approve |
|---|---|---|---|---|---|
| Drafts List | ✅ | ✅ | ❌ | ❌ | ❌ |
| Approval Queue | ✅ | ❌ | ✅ | ✅ | ✅ |
| Calendar | ✅ | ❌ | ✅ | ❌ | ❌ |

Dropdown shows only relevant actions for that view.

---

## 7. States

### 7.1 Empty selection

Dropdown placeholder: "Bulk Actions" — disabled placeholder. Apply button greyed out.

### 7.2 Delete confirmation

```
┌──────────────────────────────────────────────┐
│  Delete 3 posts?                              │
│                                               │
│  You are about to delete 3 posts and          │
│  their associated publishing tasks.           │
│  This action is irreversible. Proceed?        │
│                                               │
│  [Cancel]  [Delete 3 Posts] (red)             │
└──────────────────────────────────────────────┘
```

Other actions (Send to Queue, Publish, Reject) happen immediately with no confirmation — just a toast/refresh.

### 7.3 Loading / error

- Apply button shows a spinner during HTMX request (`hx-indicator`)
- Failed posts get a toast: "2 posts deleted, 1 failed"
- On success, the view refreshes via `HX-Trigger: bulkActionComplete` and selection clears

### 7.4 Empty list

No change to existing empty state — the header bar with dropdown is simply hidden (no posts = no checkboxes to show).

---

## 8. Files to touch

### New files

| File | Purpose |
|---|---|
| `apps/composer/templates/composer/partials/bulk_header.html` | Reusable header bar + dropdown + Apply button + hidden form + delete modal. Can be `{% include %}` in any post list view. |

### Modified files

| File | Change |
|---|---|
| `templates/composer/drafts_list.html` | Add Alpine scope, checkbox per row, `{% include "composer/partials/bulk_header.html" %}` above list |
| `templates/approvals/queue.html` | Replace floating bar with header dropdown, keep backend |
| `apps/composer/views.py` | Add `posts_bulk_action` view |
| `apps/composer/urls.py` | Add `posts/bulk-action/` route |

---

## 9. Decisions (Answered)

1. **Views that get bulk actions:** Drafts List, Approval Queue, Approvals (org), Sent (published). Calendar does NOT get bulk actions.
2. **Reject modal:** Small `<dialog>`, similar to delete modal, with a 255-char text note: *"Please provide the rejection reason for all selected posts."* [text note] [Reject] [Cancel]
3. **Row click:** Remove the full-row `<a>` wrapper entirely. Put the `<a>` only around the post title/caption text. Checkbox gets a clean click target.
4. **Pagination scope:** Drafts List + Approval Queue + Approvals + Sent views all get 25/50/100 pagination on this pass.