from django.urls import path

from .views import LineAllocationReleaseView, RegistrationHubView

app_name = "allocations"

urlpatterns = [
    path("", RegistrationHubView.as_view(), name="allocation_list"),
    path(
        "<int:pk>/release/",
        LineAllocationReleaseView.as_view(),
        name="allocation_release",
    ),
]
