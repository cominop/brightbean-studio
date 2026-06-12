"""Org-level platform credential management views.

Three responsibilities:

1. **List** every PlatformCredential in the org, showing masked secrets.
2. **Create/Update** a credential via an Alpine modal — platform selector,
   client_id + client_secret fields.
3. **Delete** a credential, reverting that platform to .env fallback.

Every mutation validates the platform choice and org membership server-side.
Credentials are stored encrypted at rest via EncryptedJSONField.
"""

from __future__ import annotations

import functools

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.credentials.models import PlatformCredential
from apps.members.models import has_org_permission

# ---------------------------------------------------------------------------
# Authorization decorator
# ---------------------------------------------------------------------------


def _require_manage_api_keys(view_func):
    """Gate on org-level ``manage_api_keys`` permission.

    Reuses the same permission as the API Keys page — both are
    org-admin-level settings operations.  Works with
    ``request.org_membership`` from the RBAC middleware.
    """

    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        org_membership = getattr(request, "org_membership", None)
        if not has_org_permission(org_membership, "manage_api_keys"):
            raise PermissionDenied(
                "You need the manage_api_keys org permission to manage platform credentials."
            )
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@_require_manage_api_keys
def credentials_list(request):
    """Render the credentials list page for the current org.

    Shows configured credentials with masked secret values, plus an
    'Add' button for platforms that don't yet have an org-level record.
    """
    org = request.org
    creds = PlatformCredential.objects.filter(
        organization=org, is_configured=True
    ).order_by("platform")

    configured_platforms = {c.platform for c in creds}
    all_platforms = PlatformCredential.Platform.choices

    # Build available platforms for the "add" dropdown (not yet configured
    # at the org level — the global .env fallback still works, but the user
    # wants an org-level override).
    available_platforms = [
        (value, label)
        for value, label in all_platforms
        if value not in configured_platforms
    ]

    context = {
        "settings_active": "credentials",
        "credentials": creds,
        "available_platforms": available_platforms,
    }
    return render(request, "credentials/list.html", context)


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


@_require_manage_api_keys
@require_http_methods(["POST"])
def credential_save(request):
    """Create or update an org-level platform credential.

    Expects POST params: platform, client_id, client_secret.
    If a credential already exists for this org+platform, update it.
    Sets is_configured=True automatically.
    """
    platform = (request.POST.get("platform") or "").strip()
    client_id = (request.POST.get("client_id") or "").strip()
    client_secret = (request.POST.get("client_secret") or "").strip()

    errors: list[str] = []
    if not platform:
        errors.append("Platform is required.")
    if not client_id:
        errors.append("Client ID is required.")
    if not client_secret:
        errors.append("Client Secret is required.")

    # Validate platform choice
    valid_platforms = {p.value for p in PlatformCredential.Platform}
    if platform and platform not in valid_platforms:
        errors.append(f"Invalid platform: {platform}")

    if errors:
        for e in errors:
            messages.error(request, e)
        return redirect("credentials:list")

    PlatformCredential.objects.update_or_create(
        organization=request.org,
        platform=platform,
        defaults={
            "credentials": {"client_id": client_id, "client_secret": client_secret},
            "is_configured": True,
        },
    )
    label = dict(PlatformCredential.Platform.choices).get(platform, platform)
    messages.success(request, f"Saved credentials for {label}.")
    return redirect("credentials:list")


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@_require_manage_api_keys
@require_http_methods(["POST"])
def credential_delete(request, credential_id):
    """Remove an org-level platform credential.

    After deletion the platform falls back to .env globals (or shows
    'Not Configured' if those are also absent).  The OAuth flow
    automatically picks up the change — no restart needed for DB-level
    credentials.
    """
    cred = get_object_or_404(
        PlatformCredential.objects.select_related("organization"),
        id=credential_id,
    )
    if cred.organization_id != request.org.id:
        raise Http404()

    label = cred.get_platform_display()
    cred.delete()
    messages.success(request, f"Removed credentials for {label}.")
    return redirect("credentials:list")
