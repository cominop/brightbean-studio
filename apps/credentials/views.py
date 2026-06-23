"""Org-level and workspace-level platform credential management views.

Three responsibilities:

1. **List** every PlatformCredential in the org (or workspace), showing masked secrets.
2. **Create/Update** a credential via POST — supports both org-level and workspace-scoped.
3. **Delete** a credential, reverting that platform to .env fallback.
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
from apps.members.models import has_org_permission, WorkspaceMembership
from apps.workspaces.models import Workspace

# ---------------------------------------------------------------------------
# Authorization decorator
# ---------------------------------------------------------------------------


def _require_manage_api_keys(view_func):
    """Gate on org-level ``manage_api_keys`` permission."""

    @functools.wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        org_membership = getattr(request, "org_membership", None)
        if not has_org_permission(org_membership, "manage_api_keys"):
            raise PermissionDenied(
                "You need the manage_api_keys org permission to manage platform credentials."
            )
        return view_func(request, *args, **kwargs)

    return login_required(_wrapped)


def _require_workspace_member(view_func):
    """Gate on workspace membership (editor or higher)."""

    @functools.wraps(view_func)
    def _wrapped(request, workspace_id, *args, **kwargs):
        workspace = get_object_or_404(Workspace, id=workspace_id, organization=request.org)
        membership = WorkspaceMembership.objects.filter(
            workspace=workspace, user=request.user
        ).first()
        if not membership:
            raise PermissionDenied("You are not a member of this workspace.")
        request.workspace = workspace
        return view_func(request, workspace_id, *args, **kwargs)

    return login_required(_wrapped)


# ---------------------------------------------------------------------------
# Org-level List
# ---------------------------------------------------------------------------


@_require_manage_api_keys
def credentials_list(request):
    """Render the credentials list page for the current org."""
    org = request.org
    creds = PlatformCredential.objects.filter(
        organization=org, is_configured=True
    ).order_by("workspace__name", "platform")

    configured_platforms = {c.platform for c in creds if c.workspace_id is None}
    all_platforms = PlatformCredential.Platform.choices

    available_platforms = [
        (value, label)
        for value, label in all_platforms
        if value not in configured_platforms
    ]

    # Split into org-level and workspace-scoped
    workspace_creds = [c for c in creds if c.workspace_id is not None]
    org_creds = [c for c in creds if c.workspace_id is None]

    context = {
        "settings_active": "credentials",
        "credentials": org_creds,
        "workspace_credentials": workspace_creds,
        "available_platforms": available_platforms,
    }
    return render(request, "credentials/list.html", context)


# ---------------------------------------------------------------------------
# Workspace-level List
# ---------------------------------------------------------------------------


@_require_workspace_member
def workspace_credentials_list(request, workspace_id):
    """Render workspace-scoped credentials page."""
    workspace = request.workspace

    workspace_creds = PlatformCredential.objects.filter(
        workspace=workspace, is_configured=True
    ).order_by("platform")

    configured = {c.platform for c in workspace_creds}
    all_platforms = PlatformCredential.Platform.choices
    available = [(v, l) for v, l in all_platforms if v not in configured]

    # Show org-level creds that apply as fallback
    org_creds = PlatformCredential.objects.filter(
        organization=workspace.organization, workspace__isnull=True, is_configured=True
    ).order_by("platform")

    context = {
        "settings_active": "credentials",
        "workspace": workspace,
        "credentials": workspace_creds,
        "org_credentials": org_creds,
        "available_platforms": available,
    }
    return render(request, "credentials/workspace_list.html", context)


# ---------------------------------------------------------------------------
# Create / Update (supports both org-level and workspace-scoped)
# ---------------------------------------------------------------------------


def _credential_save_impl(request, workspace_id=None):
    """Shared save logic for org-level and workspace-scoped credentials."""
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

    valid_platforms = {p.value for p in PlatformCredential.Platform}
    if platform and platform not in valid_platforms:
        errors.append(f"Invalid platform: {platform}")

    if errors:
        for e in errors:
            messages.error(request, e)
        if workspace_id:
            return redirect("credentials:workspace_list", workspace_id=workspace_id)
        return redirect("credentials:list")

    workspace = None
    if workspace_id:
        workspace = get_object_or_404(Workspace, id=workspace_id, organization=request.org)
        PlatformCredential.objects.update_or_create(
            organization=request.org,
            workspace=workspace,
            platform=platform,
            defaults={
                "credentials": {"client_id": client_id, "client_secret": client_secret},
                "is_configured": True,
            },
        )
    else:
        PlatformCredential.objects.update_or_create(
            organization=request.org,
            workspace__isnull=True,
            platform=platform,
            defaults={
                "workspace": None,
                "credentials": {"client_id": client_id, "client_secret": client_secret},
                "is_configured": True,
            },
        )

    label = dict(PlatformCredential.Platform.choices).get(platform, platform)
    scope = f"workspace {workspace.name}" if workspace else "organization"
    messages.success(request, f"Saved credentials for {label} ({scope}).")

    if workspace_id:
        return redirect("credentials:workspace_list", workspace_id=workspace_id)
    return redirect("credentials:list")


@_require_manage_api_keys
@require_http_methods(["POST"])
def credential_save(request):
    """Create or update an org-level platform credential."""
    return _credential_save_impl(request)


@_require_workspace_member
@require_http_methods(["POST"])
def workspace_credential_save(request, workspace_id):
    """Create or update a workspace-scoped platform credential."""
    return _credential_save_impl(request, workspace_id=workspace_id)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def _credential_delete_impl(request, credential_id, workspace_id=None):
    """Shared delete logic."""
    cred = get_object_or_404(
        PlatformCredential.objects.select_related("organization", "workspace"),
        id=credential_id,
    )
    if cred.organization_id != request.org.id:
        raise Http404()
    if workspace_id and str(cred.workspace_id) != str(workspace_id):
        raise Http404()

    label = cred.get_platform_display()
    cred.delete()
    messages.success(request, f"Removed credentials for {label}.")

    if workspace_id:
        return redirect("credentials:workspace_list", workspace_id=workspace_id)
    return redirect("credentials:list")


@_require_manage_api_keys
@require_http_methods(["POST"])
def credential_delete(request, credential_id):
    """Remove an org-level platform credential."""
    return _credential_delete_impl(request, credential_id)


@_require_workspace_member
@require_http_methods(["POST"])
def workspace_credential_delete(request, workspace_id, credential_id):
    """Remove a workspace-scoped platform credential."""
    return _credential_delete_impl(request, credential_id, workspace_id=workspace_id)
