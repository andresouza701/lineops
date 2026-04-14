from django.urls import path

from . import views

app_name = "pendencies"

urlpatterns = [
    path("api/detail/", views.PendencyDetailView.as_view(), name="detail"),
    path("api/update/", views.PendencyUpdateView.as_view(), name="update"),
    path("api/claim/", views.PendencyClaimView.as_view(), name="claim"),
]
