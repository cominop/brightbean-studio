# Unsplash Integration Spec — BrightBean Studio

**Date:** 2026-05-29
**Author:** Hermes + ShareHaus
**Upstream:** [brightbeanxyz/brightbean-studio#51](https://github.com/brightbeanxyz/brightbean-studio/issues/51)
**DB ready:** Yes — MediaAsset.source/source_url/attribution fields exist, no migrations needed

---

## 1. Overview

Allow users to search Unsplash for stock photography directly from the BrightBean
media library and import selected images as MediaAsset records with proper attribution.
Two entry points, one search experience, one import pipeline.

---

## 2. User Flow

### 2.1 Entry Point A — Media Library Sidebar

On the main Media Library page (`/workspace/<id>/media/`), a new button in the left
sidebar under "Starred":

```
OLDERS
  [+] All Media
  [★] Starred
  [📷] Search Unsplash...    ← NEW
```

Clicking it opens the Unsplash search modal (shared component, see §2.3).

### 2.2 Entry Point B — Media Library Dialog (Composer)

In the post composer, when the user clicks "Media Library," a modal dialog opens.
At the bottom of this dialog, add a new section:

```
┌─ Media Library ─────────────────────────────── [X] ─┐
│                                                      │
│   [existing media grid or empty state]                │
│                                                      │
│  ─────────────────────────────────────────────────── │
│   🔍 [            Search Unsplash...          ] [Go] │  ← NEW
│                                                      │
└──────────────────────────────────────────────────────┘
```

Clicking "Go" (or pressing Enter) opens the Unsplash search modal.

### 2.3 Unsplash Search Modal (shared)

A modal dialog with:

- **Search bar** at top: text input + "Search" button, pre-focused on open
- **Results grid**: thumbnail grid, 5 columns, images load from Unsplash CDN
- **Hover state**: photographer name + "Import" button overlay on each thumbnail
- **Pagination**: "Load more" button at bottom (Unsplash paginates via `page` param)
- **Attribution preview**: when an image is selected, a small banner shows
  "Photo by [Name] on Unsplash" (required by Unsplash API terms)

### 2.4 Import Flow

1. User clicks "Import" on a result
2. Backend checks dedup: `MediaAsset.objects.filter(workspace=ws, external_id=photo_id).exists()`
   → if found, return 409 with existing asset info
3. Backend downloads the image at `regular` resolution (1080px wide, good quality/speed balance)
4. Backend sends a download-tracking event to Unsplash (`POST /photos/:id/download/`
   — required by API guidelines)
5. Creates a `MediaAsset` record:
   - `external_id = photo_id` (Unsplash photo ID, for dedup)
   - `source = "unsplash"`
   - `source_url = <Unsplash photo page URL>`
   - `attribution = "Photo by {photographer} on Unsplash"`
   - `uploaded_by = <current user>`
   - `workspace = <current workspace>`
   - `organization = <current org>`
   - `alt_text = <Unsplash description>`
   - `file` = downloaded image stored to `media_library/%Y/%m/`
   - `folder = <folder_id>` if provided, else None (workspace root)
6. MediaAsset appears in the user's library immediately
7. In the composer dialog, the new asset is selectable right away

---

## 3. API Endpoints (new)

All under `/api/v1/media/unsplash/`. Token auth, same as existing posts API.

### 3.1 Search

```
GET /api/v1/media/unsplash/search/?q=coffee+shop&page=1&per_page=20&orientation=landscape&color=8B4513
```

**Parameters:**
| Param       | Type   | Default | Description                                      |
|-------------|--------|---------|--------------------------------------------------|
| q           | string | req'd   | Search query                                     |
| page        | int    | 1       | Page number (Unsplash uses 1-based)              |
| per_page    | int    | 20      | Results per page (max 30)                        |
| orientation | string | null    | landscape, portrait, or squarish                 |
| color       | string | null    | 6-char hex color without # (e.g., "8B4513")      |

**Response (200):**
```json
{
  "results": [
    {
      "id": "abc123",
      "description": "A barista pouring latte art",
      "width": 4000,
      "height": 6000,
      "color": "#8B4513",
      "urls": {
        "raw": "https://images.unsplash.com/photo-abc123",
        "regular": "https://images.unsplash.com/photo-abc123?w=1080",
        "thumb": "https://images.unsplash.com/photo-abc123?w=200"
      },
      "photographer": "Jane Doe",
      "photographer_url": "https://unsplash.com/@janedoe",
      "download_url": "https://api.unsplash.com/photos/abc123/download"
    }
  ],
  "total": 150,
  "total_pages": 8,
  "page": 1
}
```

### 3.2 Import

```
POST /api/v1/media/unsplash/import/
```

**Request body:**
```json
{
  "photo_id": "abc123",
  "workspace_id": "ddfe3751-0e98-4302-83ab-8aa9b1f9f3f1",
  "folder_id": null,
  "alt_text": "Optional override for alt text"
}
```

**Response (201):**
```json
{
  "id": "uuid-of-media-asset",
  "filename": "abc123.jpg",
  "source": "unsplash",
  "source_url": "https://unsplash.com/photos/abc123",
  "attribution": "Photo by Jane Doe on Unsplash",
  "width": 4000,
  "height": 6000,
  "file_size": 2456789,
  "url": "/media/media_library/2026/05/abc123.jpg",
  "thumbnail_url": "/media/media_library/thumbs/2026/05/abc123.jpg"
}
```

**Errors:**
- 400: Invalid photo_id
- 404: Photo not found on Unsplash
- 409: Photo already imported (by photo_id + workspace — optional dedup)
- 500: Download failed or Unsplash API error

### 3.3 Folder CRUD

Since the import endpoint accepts `folder_id`, users need to manage folders. Model
already exists (`MediaFolder`), just needs API endpoints.

```
GET    /api/v1/media/folders/                        # List folders in workspace
POST   /api/v1/media/folders/                        # Create folder
PATCH  /api/v1/media/folders/<uuid:id>/               # Rename or move (change parent)
DELETE /api/v1/media/folders/<uuid:id>/               # Delete empty folder
```

**List (GET):**
```json
{
  "results": [
    {
      "id": "uuid",
      "name": "Café Interiors",
      "parent_folder": null,
      "depth": 0,
      "asset_count": 12,
      "created_at": "2026-05-29T12:00:00Z"
    },
    {
      "id": "uuid",
      "name": "Latte Art",
      "parent_folder": "<parent-uuid>",
      "depth": 1,
      "asset_count": 5,
      "created_at": "2026-05-29T13:00:00Z"
    }
  ]
}
```

**Create (POST):**
```json
{
  "name": "Café Interiors",
  "parent_folder_id": null
}
```
Returns 201 with folder object. Validates: name unique per parent within workspace,
max 3 levels deep (enforced by model `clean()`).

**Update (PATCH):**
```json
{
  "name": "Coffee Shop Interiors",
  "parent_folder_id": "<new-parent-uuid>"
}
```

**Delete (DELETE):**
Returns 204. Only succeeds if folder is empty (no assets, no subfolders).
Returns 409 if folder has contents: `"Folder is not empty. Move or delete {n} assets first."`

### 3.4 URL routing

Add to `apps/integrations/urls.py`:
```python
path("media/unsplash/search/", views.UnsplashSearchView.as_view(), name="unsplash_search"),
path("media/unsplash/import/", views.UnsplashImportView.as_view(), name="unsplash_import"),
path("media/folders/", views.FolderListCreateView.as_view(), name="folder_list"),
path("media/folders/<uuid:id>/", views.FolderDetailView.as_view(), name="folder_detail"),
```

---

## 4. Backend Changes

### 4.1 Unsplash Service — wire up real API

Replace the stub in `apps/integrations/services/unsplash.py`:

**`UnsplashClient` class:**
- Reads `UNSPLASH_ACCESS_KEY` from `settings.UNSPLASH_ACCESS_KEY` (loaded from env)
- Rate limiting: tracks 50 req/hour free tier, returns 429 with Retry-After when exceeded
- Methods:
  - `search_photos(query, page, per_page)` → `SearchResults`
  - `get_photo(photo_id)` → `UnsplashPhoto`
  - `download_photo(photo_id)` → `bytes` (triggers Unsplash download event via `POST /photos/:id/download/`)
  - `trigger_download_event(photo_id)` → void (attribution compliance)

**Env var:** Add `UNSPLASH_ACCESS_KEY` to `.env.example` and `config/settings/base.py`

### 4.2 Views

In `apps/integrations/views.py`, add:

- `UnsplashSearchView(APIView)` — GET handler, validates query params, calls service
- `UnsplashImportView(APIView)` — POST handler, downloads + creates MediaAsset

### 4.3 MediaAsset model change

Add one field for dedup:
```python
# apps/media_library/models.py — MediaAsset
external_id = models.CharField(max_length=100, blank=True, default="",
    help_text="External ID from stock photo provider (e.g., Unsplash photo ID)")
```

Migration needed: `python manage.py makemigrations media_library`

### 4.4 MediaAsset creation

A helper function in the import view:
1. Download image bytes from Unsplash CDN
2. Create a Django `ContentFile` from bytes
3. Detect media_type from response Content-Type
4. Call `trigger_download_event()` before creating the asset (compliance)
5. Create `MediaAsset` with all attribution fields populated
6. If `folder_id` provided, set it (otherwise asset goes to workspace root)

---

## 5. Frontend Changes

### 5.1 Media Library Sidebar

File: `apps/media_library/templates/` (or wherever the sidebar template lives)

Add a link/button under Starred:
```html
<a href="#" id="unsplash-search-btn" class="sidebar-link">
  <span class="icon">📷</span> Search Unsplash...
</a>
```

HTMX or Alpine.js triggers modal open.

### 5.2 Media Library Dialog (Composer)

File: composer post-creation template

At the bottom of the media library modal, add:
```html
<div class="unsplash-search-bar">
  <input type="text" placeholder="Search Unsplash for photos..." id="unsplash-query">
  <button id="unsplash-go-btn" class="btn">Search</button>
</div>
```

### 5.3 Unsplash Search Modal (shared component)

New template: `apps/integrations/templates/integrations/unsplash_modal.html`

Structure:
```
┌─ Search Unsplash ────────────────────────────────────── [X] ┐
│ 🔍 [                coffee shop                    ] [Go]   │
│ Orient: [Any ▾]  Color: [Any ▾]                            │
│                                                             │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │
│ │      │ │      │ │      │ │      │ │      │              │
│ │ img  │ │ img  │ │ img  │ │ img  │ │ img  │              │
│ │      │ │      │ │      │ │      │ │      │              │
│ │[Imp] │ │[Imp] │ │[Imp] │ │[Imp] │ │[Imp] │              │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘              │
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐              │
│ │ ...  │ │ ...  │ │ ...  │ │ ...  │ │ ...  │              │
│ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘              │
│                                                             │
│              [ Load more results ]                          │
│                                                             │
│  Attribution: Photo by Jane Doe on Unsplash                 │
└─────────────────────────────────────────────────────────────┘
```

Behavior:
- Search on Enter or "Go" click → `GET /api/v1/media/unsplash/search/`
- Orientation dropdown: Any, Landscape, Portrait, Squarish
- Color dropdown: Any + 12 common colors (black, white, yellow, orange, red, green, blue, purple, magenta, teal, gray, brown)
- "Import" click → `POST /api/v1/media/unsplash/import/`
- On 409 (duplicate): show "Already in your library" toast, highlight existing asset
- On successful import, toast notification + close modal (or stay open to import more)
- "Load more" increments page and appends results

### 5.4 Padding Fix (media library)

File: media library main page template

- Add `pt-4` (or equivalent) to the main content container
- Add `pl-4` to the sidebar navigation section
- Verify top bar elements (search, filters, upload button) have consistent vertical spacing

---

## 6. Unsplash API Compliance

Unsplash API Guidelines (free tier):
- **Attribution**: "Photo by {name} on Unsplash" must be displayed. We store it in
  `MediaAsset.attribution` and show it in the UI when viewing asset details.
- **Download tracking**: `POST /photos/:id/download/` every time an image is imported.
  Must not be called on search — only when the user actually imports.
- **Hotlinking**: Allowed for search results (thumbnails). Imported images are stored
  locally, which is also allowed under the API terms.
- **Rate limit**: 50 requests/hour on free tier. Track locally and surface to user.
- **No competing service**: We are not building a stock photo platform — we are
  integrating into a social media tool. This falls within acceptable use.

---

## 7. Error States

| Situation | Behavior |
|-----------|----------|
| No API key configured | Both entry points hidden (graceful degradation) |
| API key invalid (401) | "Unsplash API key is invalid" message in modal |
| Rate limited (403/429) | "Rate limit reached. Try again in X minutes." |
| Network error | "Could not reach Unsplash. Check your connection." |
| Photo already imported | 409 — "Already in your media library." Response includes existing asset ID so the UI can highlight it. User can still re-import if they choose (via `force=true` param). |
| Download fails | "Failed to download image. Try another one." |

---

## 8. Dependencies

- **Python**: `requests` or `httpx` for API calls (add to `requirements.txt`)
- **Unsplash account**: developer account + app registration → access key
- **No new Django packages**: everything uses existing DRF + Django FileField machinery

---

## 9. Testing Plan

### Unit tests
- `UnsplashClient.search_photos()` — mock API responses, test pagination
- `UnsplashClient.trigger_download_event()` — verify POST call
- Import view — test MediaAsset creation with all attribution fields
- Import view — test duplicate photo handling
- Search view — test query param validation

### Integration tests
- End-to-end: search → import → MediaAsset appears in library
- Rate limit handling: mock 429 response, verify user sees retry message
- No API key: verify endpoints return 503 with helpful message

### Manual QA
- Search for "coffee shop" → verify results display
- Import a photo → verify it appears in media library with correct attribution
- Imported photo is selectable in composer dialog
- Load more pagination works
- Padding fixes render correctly at various viewport widths

---

## 10. Build Order

1. **Add `external_id` field** to MediaAsset model + migration
2. **Wire up UnsplashClient** — real API calls, env var, rate limiting, orientation/color params
3. **API endpoints** — search (with orientation/color) + import (with dedup + folder support) + tests
4. **Unsplash search modal** — shared HTML template + JS with orientation/color dropdowns
5. **Sidebar button** — entry point A
6. **Dialog search bar** — entry point B, wired to modal
7. **Padding fixes** — media library page CSS
8. **Attribution display** — asset detail view shows photographer credit
9. **409 dedup UX** — "Already in library" toast + highlight flow

---

## 11. Resolved Decisions

1. **Dedup**: ✅ **Yes** — prevent importing the same Unsplash photo twice. Add `external_id` field to MediaAsset (stores Unsplash photo ID). On import, check `external_id + workspace` before downloading. Return 409 on collision.
2. **Resolution**: ✅ **regular** (1080px wide) — good balance of quality and download speed.
3. **Folder support**: ✅ **Yes** — `folder_id` in import request body, validated against workspace. Workspace root if omitted.
4. **Filters**: ✅ **Expose** — `orientation` and `color` params on search endpoint, reflected in modal UI.
