"""DRF serializers for the integrations REST API.

Serializes Post and PlatformPost models for JSON I/O. The write path
(CreatePostSerializer) is designed for programmatic creation from Hermes /
other tools rather than the full interactive-composer experience.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.composer.models import PlatformPost, Post
from apps.social_accounts.models import SocialAccount


class PlatformPostSerializer(serializers.ModelSerializer):
    """Read/write serializer for a single PlatformPost variant."""

    platform = serializers.CharField(source="social_account.platform", read_only=True)
    account_name = serializers.CharField(source="social_account.account_name", read_only=True)

    class Meta:
        model = PlatformPost
        fields = [
            "id",
            "platform",
            "account_name",
            "social_account",
            "status",
            "scheduled_at",
            "published_at",
            "publish_error",
            "platform_specific_title",
            "platform_specific_caption",
            "platform_specific_first_comment",
            "platform_extra",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "published_at",
            "publish_error",
            "created_at",
            "updated_at",
        ]


class PostSerializer(serializers.ModelSerializer):
    """Read serializer for a Post with its platform variants nested."""

    platform_posts = PlatformPostSerializer(many=True, read_only=True)

    class Meta:
        model = Post
        fields = [
            "id",
            "workspace",
            "author",
            "title",
            "caption",
            "first_comment",
            "internal_notes",
            "tags",
            "category",
            "scheduled_at",
            "published_at",
            "created_at",
            "updated_at",
            "platform_posts",
        ]
        read_only_fields = [
            "id",
            "author",
            "published_at",
            "created_at",
            "updated_at",
        ]


class CreatePostSerializer(serializers.Serializer):
    """Serializer for creating a new Post + PlatformPosts via the API.

    Accepts:
        workspace_id    – UUID of the workspace to create the post in.
        content         – Base caption / body text.
        title           – Optional post title.
        platforms       – List of platform keys, e.g. ``["twitter", "linkedin"]``.
        media_urls      – Optional list of media URLs (URLs, not asset IDs).
        scheduled_at    – ISO 8601 datetime string for scheduling.
        tags            – Optional list of tag strings.
        first_comment   – Optional first-comment text.
        internal_notes  – Optional internal notes visible only in Studio.
        platform_variants – Optional dict mapping platform → caption override.
    """

    workspace_id = serializers.UUIDField()
    content = serializers.CharField(allow_blank=True, write_only=True, source="caption")
    title = serializers.CharField(required=False, allow_blank=True, default="")
    platforms = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    media_urls = serializers.ListField(
        child=serializers.URLField(),
        required=False,
        default=list,
    )
    scheduled_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    tags = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    first_comment = serializers.CharField(required=False, allow_blank=True, default="")
    internal_notes = serializers.CharField(required=False, allow_blank=True, default="")
    platform_variants = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        default=dict,
    )
    social_account_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Specific SocialAccount UUIDs to target. If empty, uses connected accounts matching `platforms`.",
    )

    def validate_platforms(self, value: list[str]) -> list[str]:
        valid = set(dict(PlatformPost.Status.choices).keys())  # not quite right — use SocialAccount
        # We'll accept any platform key string; validation against connected
        # accounts happens in create().
        return [p.strip().lower() for p in value if p.strip()]

    def create(self, validated_data: dict) -> Post:
        from django.utils import timezone

        workspace_id = validated_data["workspace_id"]
        platforms: list[str] = validated_data.get("platforms", [])
        social_account_ids: list = validated_data.get("social_account_ids", [])
        platform_variants: dict[str, str] = validated_data.get("platform_variants", {})
        scheduled_at = validated_data.get("scheduled_at")

        # Resolve SocialAccounts
        social_accounts = self._resolve_social_accounts(
            workspace_id, platforms, social_account_ids
        )

        # Create the Post
        post = Post.objects.create(
            workspace_id=workspace_id,
            author=self.context["request"].user if self.context.get("request") else None,
            title=validated_data.get("title", ""),
            caption=validated_data.get("caption", validated_data.get("content", "")),
            first_comment=validated_data.get("first_comment", ""),
            internal_notes=validated_data.get("internal_notes", ""),
            tags=validated_data.get("tags", []),
            scheduled_at=scheduled_at,
        )

        # Create one PlatformPost per resolved SocialAccount
        for sa in social_accounts:
            variant_caption = platform_variants.get(sa.platform)
            pp = PlatformPost.objects.create(
                post=post,
                social_account=sa,
                status=PlatformPost.Status.SCHEDULED if scheduled_at else PlatformPost.Status.DRAFT,
                platform_specific_caption=variant_caption,
                scheduled_at=scheduled_at,
            )

        # TODO: Handle media_urls — for now we store them in internal_notes
        # so the caller can see they were passed. A follow-up will create
        # PostMedia records from downloaded or referenced URLs.
        media_urls: list[str] = validated_data.get("media_urls", [])
        if media_urls:
            post.internal_notes = (
                f"{post.internal_notes}\n\n[media_urls]: {', '.join(media_urls)}"
            ).strip()
            post.save(update_fields=["internal_notes"])

        return post

    @staticmethod
    def _resolve_social_accounts(
        workspace_id, platforms: list[str], social_account_ids: list
    ) -> list[SocialAccount]:
        """Resolve which SocialAccounts to create PlatformPosts for."""
        qs = SocialAccount.objects.filter(
            workspace_id=workspace_id,
            connection_status=SocialAccount.ConnectionStatus.CONNECTED,
        )

        if social_account_ids:
            qs = qs.filter(id__in=social_account_ids)
        elif platforms:
            qs = qs.filter(platform__in=platforms)

        if not qs.exists():
            # If user explicitly asked for platforms/accounts, fail loudly.
            # If neither was specified, just create a bare post (no platforms).
            if platforms or social_account_ids:
                raise serializers.ValidationError(
                    {
                        "platforms": (
                            "No connected social accounts found for the given "
                            "workspace and platform selection."
                        )
                    }
                )
            return []

        return list(qs)


# ---------------------------------------------------------------------------
# Unsplash search / import serializers
# ---------------------------------------------------------------------------

class UnsplashPhotoResultSerializer(serializers.Serializer):
    """Individual photo result from Unsplash search."""

    id = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    color = serializers.CharField(allow_blank=True)
    urls = serializers.DictField()
    photographer = serializers.CharField()
    photographer_url = serializers.CharField()


class UnsplashSearchResponseSerializer(serializers.Serializer):
    """Full search response with pagination."""

    results = UnsplashPhotoResultSerializer(many=True)
    total = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    page = serializers.IntegerField()


class UnsplashImportRequestSerializer(serializers.Serializer):
    """Request body for importing a photo from Unsplash."""

    photo_id = serializers.CharField(required=True)
    workspace_id = serializers.UUIDField(required=True)
    folder_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    alt_text = serializers.CharField(required=False, allow_blank=True, default="")
    force = serializers.BooleanField(required=False, default=False)


class MediaAssetImportResponseSerializer(serializers.ModelSerializer):
    """Response after importing a photo as a MediaAsset."""

    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        from apps.media_library.models import MediaAsset

        model = MediaAsset
        fields = [
            "id",
            "filename",
            "source",
            "source_url",
            "attribution",
            "width",
            "height",
            "file_size",
            "url",
            "thumbnail_url",
        ]

    def get_url(self, obj):
        if obj.file:
            return obj.file.url
        return ""

    def get_thumbnail_url(self, obj):
        if obj.thumbnail:
            return obj.thumbnail.url
        return ""


# ---------------------------------------------------------------------------
# Folder serializers
# ---------------------------------------------------------------------------

class MediaFolderSerializer(serializers.Serializer):
    """Read/write serializer for MediaFolder."""

    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=255)
    workspace_id = serializers.UUIDField(write_only=True, required=False)
    parent_folder_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    parent_folder = serializers.UUIDField(source="parent_folder_id", read_only=True)
    depth = serializers.IntegerField(read_only=True)
    asset_count = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def get_asset_count(self, obj):
        return getattr(obj, "asset_count", obj.assets.count())

    def create(self, validated_data):
        from apps.media_library.models import MediaFolder
        from apps.workspaces.models import Workspace

        workspace_id = validated_data.pop("workspace_id", None)
        parent_folder_id = validated_data.pop("parent_folder_id", None)

        workspace = Workspace.objects.get(id=workspace_id)
        parent_folder = None
        if parent_folder_id:
            parent_folder = MediaFolder.objects.get(id=parent_folder_id)

        folder = MediaFolder(
            workspace=workspace,
            organization=workspace.organization,
            parent_folder=parent_folder,
            **validated_data,
        )
        folder.clean()
        folder.save()
        return folder

    def update(self, instance, validated_data):
        parent_folder_id = validated_data.pop("parent_folder_id", None)
        if parent_folder_id is not None:
            from apps.media_library.models import MediaFolder

            instance.parent_folder = MediaFolder.objects.get(id=parent_folder_id)

        for attr, value in validated_data.items():
            if attr != "workspace_id":
                setattr(instance, attr, value)

        instance.clean()
        instance.save()
        return instance
