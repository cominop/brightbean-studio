"""Tests for the integrations REST API."""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.composer.models import PlatformPost, Post
from apps.members.models import OrgMembership, WorkspaceMembership
from apps.organizations.models import Organization
from apps.social_accounts.models import SocialAccount
from apps.workspaces.models import Workspace


class ApiPostTests(TestCase):
    """Tests for POST /api/v1/posts/ and GET /api/v1/posts/."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="api-tester@example.com",
            password="testpass123",
            tos_accepted_at=timezone.now(),
        )
        self.org = Organization.objects.create(name="API Test Org")
        self.workspace = Workspace.objects.create(
            organization=self.org, name="API Test Workspace"
        )
        OrgMembership.objects.create(
            user=self.user,
            organization=self.org,
            org_role=OrgMembership.OrgRole.OWNER,
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
        )

        # Create connected social accounts
        self.twitter_account = SocialAccount.objects.create(
            workspace=self.workspace,
            platform="twitter",
            account_platform_id="tw-1",
            account_name="Test Twitter",
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        )
        self.linkedin_account = SocialAccount.objects.create(
            workspace=self.workspace,
            platform="linkedin_personal",
            account_platform_id="li-1",
            account_name="Test LinkedIn",
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        )

        # Auth token
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.list_url = reverse("integrations:api_post_list")

    def test_unauthorized_request_returns_401(self):
        """Requests without a valid token should return 401."""
        client = APIClient()  # no token
        response = client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_create_post_with_platforms(self):
        """Create a post targeting specific platforms via SocialAccount IDs."""
        payload = {
            "workspace_id": str(self.workspace.id),
            "content": "Hello from the API!",
            "title": "API Test Post",
            "platforms": ["twitter", "linkedin_personal"],
            "tags": ["api", "test"],
            "social_account_ids": [
                str(self.twitter_account.id),
                str(self.linkedin_account.id),
            ],
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)

        data = response.json()
        self.assertEqual(data["caption"], "Hello from the API!")
        self.assertEqual(data["title"], "API Test Post")
        self.assertEqual(data["tags"], ["api", "test"])
        self.assertEqual(len(data["platform_posts"]), 2)

        # Verify PlatformPosts in DB
        post = Post.objects.get(id=data["id"])
        platform_posts = post.platform_posts.all()
        self.assertEqual(platform_posts.count(), 2)
        platforms = {pp.social_account.platform for pp in platform_posts}
        self.assertEqual(platforms, {"twitter", "linkedin_personal"})
        # They should be in draft status (no scheduled_at)
        for pp in platform_posts:
            self.assertEqual(pp.status, PlatformPost.Status.DRAFT)

    def test_create_post_with_scheduled_at(self):
        """Posts with scheduled_at get PlatformPosts in 'scheduled' status."""
        future = timezone.now() + timedelta(days=1)
        payload = {
            "workspace_id": str(self.workspace.id),
            "content": "Scheduled post",
            "platforms": ["twitter"],
            "social_account_ids": [str(self.twitter_account.id)],
            "scheduled_at": future.isoformat(),
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)

        data = response.json()
        pp = data["platform_posts"][0]
        self.assertEqual(pp["status"], "scheduled")

    def test_list_posts(self):
        """GET /api/v1/posts/ returns posts for the user's workspaces."""
        # Create a couple of posts
        Post.objects.create(
            workspace=self.workspace,
            author=self.user,
            caption="Post A",
        )
        Post.objects.create(
            workspace=self.workspace,
            author=self.user,
            caption="Post B",
        )
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 2)

    def test_list_posts_filtered_by_platform(self):
        """GET /api/v1/posts/?platform=twitter filters correctly."""
        post = Post.objects.create(
            workspace=self.workspace,
            author=self.user,
            caption="Twitter post",
        )
        PlatformPost.objects.create(
            post=post,
            social_account=self.twitter_account,
            status=PlatformPost.Status.PUBLISHED,
        )
        response = self.client.get(f"{self.list_url}?platform=twitter")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 1)
        self.assertTrue(
            any(
                pp["platform"] == "twitter"
                for item in data
                for pp in item["platform_posts"]
            )
        )

    def test_get_post_detail(self):
        """GET /api/v1/posts/<id>/ returns post detail."""
        post = Post.objects.create(
            workspace=self.workspace,
            author=self.user,
            caption="Detail test",
        )
        url = reverse("integrations:api_post_detail", kwargs={"id": post.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["caption"], "Detail test")

    def test_patch_post(self):
        """PATCH /api/v1/posts/<id>/ updates allowed fields."""
        post = Post.objects.create(
            workspace=self.workspace,
            author=self.user,
            caption="Original caption",
            title="Old Title",
        )
        url = reverse("integrations:api_post_detail", kwargs={"id": post.id})
        response = self.client.patch(
            url,
            {"caption": "Updated caption", "title": "New Title"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["caption"], "Updated caption")
        self.assertEqual(data["title"], "New Title")

    def test_create_post_no_social_accounts_returns_error(self):
        """When no matching connected accounts exist, return a validation error."""
        # Use a workspace with no connected accounts
        empty_ws = Workspace.objects.create(
            organization=self.org, name="Empty Workspace"
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=empty_ws,
            workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
        )
        payload = {
            "workspace_id": str(empty_ws.id),
            "content": "Test",
            "platforms": ["twitter"],
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 400)

    def test_create_post_with_platform_variants(self):
        """Platform-specific caption overrides are stored on PlatformPost."""
        payload = {
            "workspace_id": str(self.workspace.id),
            "content": "Base caption",
            "platforms": ["twitter", "linkedin_personal"],
            "social_account_ids": [
                str(self.twitter_account.id),
                str(self.linkedin_account.id),
            ],
            "platform_variants": {
                "twitter": "Short tweet version",
                "linkedin_personal": "Long LinkedIn version",
            },
        }
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, 201)

        data = response.json()
        for pp in data["platform_posts"]:
            if pp["platform"] == "twitter":
                self.assertEqual(
                    pp["platform_specific_caption"], "Short tweet version"
                )
            elif pp["platform"] == "linkedin_personal":
                self.assertEqual(
                    pp["platform_specific_caption"], "Long LinkedIn version"
                )


# ---------------------------------------------------------------------------
# Unsplash search, import, and folder CRUD tests
# ---------------------------------------------------------------------------

import uuid

from apps.media_library.models import MediaFolder


class UnsplashApiTests(TestCase):
    """Tests for Unsplash search, Unsplash import, and MediaFolder CRUD."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="unsplash-tester@example.com",
            password="testpass123",
            tos_accepted_at=timezone.now(),
        )
        self.org = Organization.objects.create(name="Unsplash Test Org")
        self.workspace = Workspace.objects.create(
            organization=self.org, name="Unsplash Test Workspace"
        )
        OrgMembership.objects.create(
            user=self.user,
            organization=self.org,
            org_role=OrgMembership.OrgRole.OWNER,
        )
        WorkspaceMembership.objects.create(
            user=self.user,
            workspace=self.workspace,
            workspace_role=WorkspaceMembership.WorkspaceRole.OWNER,
        )

        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        # Pre-create a folder for detail operations
        self.folder = MediaFolder.objects.create(
            workspace=self.workspace,
            organization=self.org,
            name="Test Folder",
        )

        # URL names
        self.search_url = reverse("integrations:unsplash_search")
        self.import_url = reverse("integrations:unsplash_import")
        self.folder_list_url = reverse("integrations:folder_list")
        self.folder_detail_url = reverse(
            "integrations:folder_detail", kwargs={"id": self.folder.id}
        )

    # ------------------------------------------------------------------
    # Unsplash search tests
    # ------------------------------------------------------------------

    def test_search_requires_auth(self):
        """GET /media/unsplash/search/ without token returns 401."""
        unauth_client = APIClient()
        resp = unauth_client.get(self.search_url)
        self.assertEqual(resp.status_code, 401)

    def test_search_requires_query(self):
        """GET /media/unsplash/search/ without q param returns 400."""
        resp = self.client.get(self.search_url)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_search_no_api_key(self):
        """Search when UNSPLASH_ACCESS_KEY is not set returns 503."""
        resp = self.client.get(f"{self.search_url}?q=cats")
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("not configured", data["error"])

    def test_search_with_pagination_params(self):
        """Search accepts page, per_page, orientation params but still fails on
        missing API key (503), proving the params are parsed correctly first."""
        resp = self.client.get(
            f"{self.search_url}?q=cats&page=2&per_page=10&orientation=landscape"
        )
        # Still 503 because no API key, but not 400 (params are valid)
        self.assertEqual(resp.status_code, 503)

    def test_search_invalid_orientation(self):
        """Search with invalid orientation returns 400 before checking API key."""
        resp = self.client.get(f"{self.search_url}?q=cats&orientation=diagonal")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Invalid orientation", resp.json()["error"])

    # ------------------------------------------------------------------
    # Unsplash import tests
    # ------------------------------------------------------------------

    def test_import_requires_auth(self):
        """POST /media/unsplash/import/ without token returns 401."""
        unauth_client = APIClient()
        resp = unauth_client.post(self.import_url, {}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_import_requires_photo_id(self):
        """POST without photo_id returns 400 (serializer validation)."""
        resp = self.client.post(
            self.import_url,
            {"workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_import_requires_workspace_id(self):
        """POST without workspace_id returns 400 (serializer validation)."""
        resp = self.client.post(
            self.import_url,
            {"photo_id": "abc123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_import_no_api_key(self):
        """Import when UNSPLASH_ACCESS_KEY is not set returns 503."""
        resp = self.client.post(
            self.import_url,
            {
                "photo_id": "abc123",
                "workspace_id": str(self.workspace.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("not configured", data["error"])

    def test_import_nonexistent_workspace(self):
        """Import with a workspace that doesn't exist returns 404.
        This is reached before the API key check because workspace
        resolution happens after serializer validation but before
        the UnsplashClient is created."""
        bad_ws_id = uuid.uuid4()
        resp = self.client.post(
            self.import_url,
            {
                "photo_id": "abc123",
                "workspace_id": str(bad_ws_id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("Workspace not found", resp.json()["error"])

    # ------------------------------------------------------------------
    # Folder list / create tests
    # ------------------------------------------------------------------

    def test_folder_list_requires_auth(self):
        """GET /media/folders/ without token returns 401."""
        unauth_client = APIClient()
        resp = unauth_client.get(self.folder_list_url)
        self.assertEqual(resp.status_code, 401)

    def test_folder_list_requires_workspace_id(self):
        """GET /media/folders/ without workspace_id returns 400."""
        resp = self.client.get(self.folder_list_url)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("workspace_id", resp.json()["error"])

    def test_folder_list_empty(self):
        """GET with workspace_id returns results (at least the setUp folder)."""
        resp = self.client.get(
            f"{self.folder_list_url}?workspace_id={self.workspace.id}"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        # We created one folder in setUp
        self.assertGreaterEqual(len(data["results"]), 1)

    def test_folder_create(self):
        """POST creates a folder and returns 201."""
        resp = self.client.post(
            self.folder_list_url,
            {
                "name": "API Created Folder",
                "workspace_id": str(self.workspace.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "API Created Folder")
        self.assertIn("id", data)

        # Verify in DB
        self.assertTrue(
            MediaFolder.objects.filter(
                workspace=self.workspace, name="API Created Folder"
            ).exists()
        )

    def test_folder_create_requires_auth(self):
        """POST /media/folders/ without token returns 401."""
        unauth_client = APIClient()
        resp = unauth_client.post(
            self.folder_list_url,
            {"name": "No Auth Folder", "workspace_id": str(self.workspace.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_folder_create_duplicate_name(self):
        """POST with duplicate name in same parent raises IntegrityError
        (the DB-level UniqueConstraint catches it; the serializer does not
        convert this to a 400 — it propagates as a DB error)."""
        parent = MediaFolder.objects.create(
            workspace=self.workspace,
            organization=self.org,
            name="Parent Folder",
        )
        MediaFolder.objects.create(
            workspace=self.workspace,
            organization=self.org,
            name="Child Folder",
            parent_folder=parent,
        )
        # Try to create another child with the same name under the same parent
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            self.client.post(
                self.folder_list_url,
                {
                    "name": "Child Folder",
                    "workspace_id": str(self.workspace.id),
                    "parent_folder_id": str(parent.id),
                },
                format="json",
            )

    # ------------------------------------------------------------------
    # Folder detail tests — PATCH / DELETE
    # ------------------------------------------------------------------

    def test_folder_detail_requires_auth(self):
        """PATCH/DELETE without token returns 401."""
        unauth_client = APIClient()

        patch_resp = unauth_client.patch(
            self.folder_detail_url, {"name": "Renamed"}, format="json"
        )
        self.assertEqual(patch_resp.status_code, 401)

        delete_resp = unauth_client.delete(self.folder_detail_url)
        self.assertEqual(delete_resp.status_code, 401)

    def test_folder_rename(self):
        """PATCH updates the folder name successfully."""
        resp = self.client.patch(
            self.folder_detail_url, {"name": "Renamed Folder"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "Renamed Folder")

        # Verify in DB
        self.folder.refresh_from_db()
        self.assertEqual(self.folder.name, "Renamed Folder")

    def test_folder_delete_empty(self):
        """DELETE on an empty folder returns 204."""
        empty = MediaFolder.objects.create(
            workspace=self.workspace,
            organization=self.org,
            name="Empty Folder",
        )
        url = reverse("integrations:folder_detail", kwargs={"id": empty.id})
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 204)

        # Verify it's gone
        self.assertFalse(MediaFolder.objects.filter(id=empty.id).exists())

    def test_folder_nonexistent_returns_404(self):
        """PATCH/DELETE on an invalid UUID returns 404.
        (FolderDetailView only supports PATCH and DELETE; GET would return 405.)"""
        bad_id = uuid.uuid4()
        url = reverse("integrations:folder_detail", kwargs={"id": bad_id})

        patch_resp = self.client.patch(url, {"name": "Nope"}, format="json")
        self.assertEqual(patch_resp.status_code, 404)

        delete_resp = self.client.delete(url)
        self.assertEqual(delete_resp.status_code, 404)

    def test_folder_patch_parent_requires_auth(self):
        """PATCH without auth returns 401 (separate from detail auth test)."""
        unauth_client = APIClient()
        resp = unauth_client.patch(
            self.folder_detail_url, {"name": "No"}, format="json"
        )
        self.assertEqual(resp.status_code, 401)

    def test_folder_delete_requires_auth(self):
        """DELETE without auth returns 401 (separate from detail auth test)."""
        unauth_client = APIClient()
        resp = unauth_client.delete(self.folder_detail_url)
        self.assertEqual(resp.status_code, 401)
