from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from config.views import (
    HealthCheckView,
    LogoutGetView,
    UploadView,
)
from users.views import AdminOnlyView
from whatsapp.views import MeowWebhookView, WhatsAppOperationsView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    path("accounts/logout/", LogoutGetView.as_view(), name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("employees/", include("employees.urls")),
    path("telecom/", include("telecom.urls")),
    path("allocations/", include("allocations.urls")),
    path("upload/", UploadView.as_view(), name="upload"),
    path(
        "whatsapp/operacao/",
        WhatsAppOperationsView.as_view(),
        name="whatsapp_operations",
    ),
    path(
        "api/whatsapp/meow/webhook/",
        MeowWebhookView.as_view(),
        name="whatsapp_meow_webhook",
    ),
    path(
        "api/whatsapp/meow/webhook/<str:webhook_token>/",
        MeowWebhookView.as_view(),
        name="whatsapp_meow_webhook_tokenized",
    ),
    path("health/", HealthCheckView.as_view(), name="health"),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/admin-only/", AdminOnlyView.as_view(), name="admin_only"),
]

handler403 = "config.views.custom_permission_denied_view"
handler404 = "config.views.custom_page_not_found_view"
