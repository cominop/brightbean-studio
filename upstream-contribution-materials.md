# BrightBean Studio — Upstream Contribution Materials

## GitHub Discussion — Workspace-Scoped Credentials

**Suggested title:** `[Idea] Workspace-scoped OAuth credentials (per-workspace platform apps)`

**Body:**

> **Feature idea:** Allow workspaces within an organization to use different OAuth apps for the same social platform.
>
> **Why:** A multi-brand agency or a holding company running multiple coffee brands under one BrightBean org needs each workspace to authenticate with its own LinkedIn Company Page, Facebook Business page, or Pinterest account — not share a single global credential pair.
>
> **What we built locally:**
> - Added a nullable `workspace` FK to `PlatformCredential` (the existing credentials model)
> - 3-tier credential resolution: workspace → org → env var fallback
> - Workspace-level credentials panel under Workspace Settings > Credentials
> - Updated the provider resolution in both `social_accounts/views.py` (OAuth flow) and `publisher/engine.py` (publishing auth)
>
> **Affected files:**
> - `apps/credentials/models.py` — `workspace` FK + migration
> - `apps/credentials/views.py` — workspace-scoped CRUD views
> - `apps/credentials/urls.py` — new routes
> - `apps/publisher/engine.py` — resolution chain update
> - `apps/social_accounts/views.py` — OAuth redirect picks workspace-level creds
> - `templates/credentials/workspace_list.html` — new partial template
>
> **Open questions for maintainers:**
> 1. Would you prefer a different resolution strategy (e.g., explicit priority field instead of implicit FK)?
> 2. Should workspace credentials be manageable via the Agent API, or is web-only sufficient?
>
> Happy to open a PR if this direction aligns.

---

## GitHub Discussion — Unsplash API Key Configuration UI

**Suggested title:** `[Idea] In-app Unsplash API key configuration (per-workspace or global)`

**Body:**

> **Feature idea:** A web UI for configuring the `UNSPLASH_ACCESS_KEY` so workspace admins can set it from within the app rather than editing `.env` files or Railway environment variables.
>
> **Why:** The Unsplash integration (PR #55) is fully functional, but the API key is currently locked to an environment variable. For hosted/Railway users, changing the key requires a redeploy. For multi-tenant users, there's no path to use different Unsplash keys per workspace.
>
> **What we propose:**
> - A Settings > Integrations page (or an addendum to the existing Credentials panel at `/credentials/`)
> - A form field for the Unsplash API key, stored per-workspace in the database
> - Updated `_resolve_workspace_unsplash_key` in `apps/unsplash/views.py` to pull from the new storage
> - The `UnsplashClient` resolution chain (passed key → workspace key → env var) already supports this — only the storage and UI are missing
>
> **Affected areas:**
> - `apps/unsplash/views.py` — `_resolve_workspace_unsplash_key` fix + DB-backed lookup
> - New model or existing model extension for key storage
> - New template for key configuration form
> - Workspace Settings navigation integration
>
> **Open question:** Should the Unsplash key field live on the existing `/credentials/` page (renaming it to "Integrations"), or on a dedicated new Integrations page?

---

## PR Description — Workspace-Scoped Credentials

**Title:** `feat: workspace-scoped platform credentials`

**Body:**

```
## Summary

Adds per-workspace OAuth credential overrides, enabling workspaces within
the same organization to use different OAuth apps for the same social
platform. Resolution order: workspace → org → env var.

## Changes

### Model
- `PlatformCredential.workspace` — nullable FK to `workspaces.Workspace`
- `Meta.unique_together = ("org", "platform", "workspace")` — one credential
  per platform per workspace, with `workspace=NULL` for org-level defaults
- Auto-migration included

### Views
- `credentials/views.py` — new workspace-scoped CRUD endpoints:
  - `workspace_credentials_list` — list per-workspace credentials
  - `workspace_credential_create` — create (platform dropdown filtered to
    unconfigured platforms)
  - `workspace_credential_edit` — edit existing (platform locked)
  - `workspace_credential_delete` — delete with confirmation
- Rejects creation if the workspace already has a credential for that platform

### Provider Resolution
- `publisher/engine.py` — `_resolve_platform_credentials()` now checks:
  1. Workspace-level (`workspace_id=..., platform=..., is_configured=True`)
  2. Org-level (`org=..., workspace__isnull=True, is_configured=True`)
  3. Fallback to `settings.PLATFORM_CREDENTIALS_FROM_ENV`
- `social_accounts/views.py` — OAuth redirect builder also updated to
  use the same 3-tier resolution

### Templates
- `templates/credentials/workspace_list.html` — workspace credentials page
  with add/edit/delete, filtering by workspace
- `templates/credentials/list.html` — org-level list unchanged, link to
  workspace-level added

### URLS
- `credentials/urls.py` — new routes under `/workspaces/<id>/credentials/`

## Testing
- Manual: verified credential resolution sees workspace override before
  org-level or env var
- Org-level credentials remain fully functional (backwards compatible)
- Workspace-level credentials survive org switching

## Screenshots
[Attach]

Closes #<issue>
```

---

## PR Description — Unsplash API Key Configuration UI

**Title:** `feat: in-app Unsplash API key configuration`

**Body:**

```
## Summary

Adds a UI for workspace admins to configure the Unsplash API key from
within the BrightBean web app, eliminating the need for .env edits or
Railway redeploys to change keys.

## Changes

### Model
- New `WorkspaceSetting` model (or extends existing
  `settings_manager.WorkspaceSetting`) to store `unsplash_access_key`
  per workspace

### Views
- `UnsplashSettingsView` — GET/POST form for updating the key
- Updated `_resolve_workspace_unsplash_key` in `apps/unsplash/views.py`
  to query the new storage instead of crashing on `integration_settings`

### Service Layer
- `UnsplashClient` resolution chain already accepts `workspace_key` as
  a constructor parameter (second priority, after explicit key, before
  env var) — no changes needed

### Templates
- Integration settings form: input field + save button + "Test Connection" button

### URLs
- New route under workspace settings: `/workspaces/<id>/settings/unsplash/`

## Why not just .env?
- Railway users need a redeploy to change env vars
- Multi-tenant orgs may want different Unsplash keys per workspace
- DB-stored settings are the pattern the app already uses for workspace
  preferences

## Testing
- Manual: set key → verify Unsplash search returns results
- Clear key → verify search returns 503 "not configured"
- Test Connection button validates the key against Unsplash API before saving

Closes #<issue>
```