"""URL routing for the integrations API.

All routes live under /api/v1/.
"""

from django.urls import path

from . import views

app_name = "integrations"

urlpatterns = [
    path("posts/", views.PostListCreateView.as_view(), name="api_post_list"),
    path("posts/<uuid:id>/", views.PostDetailView.as_view(), name="api_post_detail"),
    # Unsplash integration
    path("media/unsplash/search/", views.UnsplashSearchView.as_view(), name="unsplash_search"),
    path("media/unsplash/import/", views.UnsplashImportView.as_view(), name="unsplash_import"),
    # Folder CRUD
    path("media/folders/", views.FolderListCreateView.as_view(), name="folder_list"),
    path("media/folders/<uuid:id>/", views.FolderDetailView.as_view(), name="folder_detail"),
]
