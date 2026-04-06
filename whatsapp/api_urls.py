from django.urls import path

from whatsapp.api_views import (
    WhatsAppIntegrationDeleteSessionApiView,
    WhatsAppIntegrationDetailApiView,
    WhatsAppIntegrationGenerateQrApiView,
    WhatsAppIntegrationListCreateApiView,
    WhatsAppIntegrationStatusApiView,
)

app_name = "whatsapp_api"

urlpatterns = [
    path("", WhatsAppIntegrationListCreateApiView.as_view(), name="list_create"),
    path("<int:session_pk>/", WhatsAppIntegrationDetailApiView.as_view(), name="detail"),
    path(
        "<int:session_pk>/status/",
        WhatsAppIntegrationStatusApiView.as_view(),
        name="status",
    ),
    path(
        "<int:session_pk>/generate-qr/",
        WhatsAppIntegrationGenerateQrApiView.as_view(),
        name="generate_qr",
    ),
    path(
        "<int:session_pk>/session/",
        WhatsAppIntegrationDeleteSessionApiView.as_view(),
        name="delete_session",
    ),
]
