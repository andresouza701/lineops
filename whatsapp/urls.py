from django.urls import path

from whatsapp.views import (
    WhatsAppSessionConnectView,
    WhatsAppSessionDisconnectView,
    WhatsAppSessionQRCodeView,
    WhatsAppSessionStatusView,
)

app_name = "whatsapp"

urlpatterns = [
    path("status/", WhatsAppSessionStatusView.as_view(), name="status"),
    path("qr/", WhatsAppSessionQRCodeView.as_view(), name="qr"),
    path("connect/", WhatsAppSessionConnectView.as_view(), name="connect"),
    path(
        "disconnect/",
        WhatsAppSessionDisconnectView.as_view(),
        name="disconnect",  # noqa: E501
    ),
]
