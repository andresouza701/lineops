from django.urls import path

from .views import (
    AllocationEditView,
    LineAllocationReleaseView,
    RegistrationHubView,
)

app_name = "allocations"

urlpatterns = [
    path("", RegistrationHubView.as_view(), name="allocation_list"),
    path(
        "<int:pk>/release/",
        LineAllocationReleaseView.as_view(),
        name="allocation_release",
    ),
    path(
        "<int:pk>/edit/",
        AllocationEditView.as_view(),
        name="allocation_edit",
    ),
]
