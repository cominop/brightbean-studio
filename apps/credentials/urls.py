from django.urls import path

from . import views

app_name = "credentials"

urlpatterns = [
    # Org-level
    path("", views.credentials_list, name="list"),
    path("save/", views.credential_save, name="save"),
    path("delete/<uuid:credential_id>/", views.credential_delete, name="delete"),
    # Workspace-scoped
    path("<uuid:workspace_id>/", views.workspace_credentials_list, name="workspace_list"),
    path("<uuid:workspace_id>/save/", views.workspace_credential_save, name="workspace_save"),
    path("<uuid:workspace_id>/delete/<uuid:credential_id>/", views.workspace_credential_delete, name="workspace_delete"),
]
