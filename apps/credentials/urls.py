from django.urls import path

from . import views

app_name = "credentials"

urlpatterns = [
    path("", views.credentials_list, name="list"),
    path("save/", views.credential_save, name="save"),
    path("delete/<uuid:credential_id>/", views.credential_delete, name="delete"),
]
