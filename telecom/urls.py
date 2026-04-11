from django.urls import path

from .views import (
    BlipConfigurationCreateView,
    BlipConfigurationListView,
    BlipConfigurationUpdateView,
    ExportPhoneLinesCSVView,
    PhoneLineCreateView,
    PhoneLineReconnectCancelView,
    PhoneLineReconnectStartView,
    PhoneLineReconnectStatusView,
    PhoneLineReconnectSubmitCodeView,
    PhoneLineDeleteView,
    PhoneLineDetailView,
    PhoneLineHistoryView,
    PhoneLineUpdateView,
    SIMcardCreateView,
    SIMcardListView,
    SIMcardUpdateView,
    TelecomOverviewView,
)

app_name = "telecom"

urlpatterns = [
    path("", TelecomOverviewView.as_view(), name="overview"),
    path(
        "blip-configurations/",
        BlipConfigurationListView.as_view(),
        name="blip_configuration_list",
    ),
    path(
        "blip-configurations/create/",
        BlipConfigurationCreateView.as_view(),
        name="blip_configuration_create",
    ),
    path(
        "blip-configurations/<int:pk>/update/",
        BlipConfigurationUpdateView.as_view(),
        name="blip_configuration_update",
    ),
    path("simcards/", SIMcardListView.as_view(), name="simcard_list"),
    path("phonelines/create/", PhoneLineCreateView.as_view(), name="phoneline_create"),
    path(
        "phonelines/<int:pk>/", PhoneLineDetailView.as_view(), name="phoneline_detail"
    ),
    path(
        "phonelines/<int:pk>/reconnect/status/",
        PhoneLineReconnectStatusView.as_view(),
        name="phoneline_reconnect_status",
    ),
    path(
        "phonelines/<int:pk>/reconnect/start/",
        PhoneLineReconnectStartView.as_view(),
        name="phoneline_reconnect_start",
    ),
    path(
        "phonelines/<int:pk>/reconnect/code/",
        PhoneLineReconnectSubmitCodeView.as_view(),
        name="phoneline_reconnect_submit_code",
    ),
    path(
        "phonelines/<int:pk>/reconnect/cancel/",
        PhoneLineReconnectCancelView.as_view(),
        name="phoneline_reconnect_cancel",
    ),
    path(
        "phonelines/<int:pk>/update/",
        PhoneLineUpdateView.as_view(),
        name="phoneline_update",
    ),
    path(
        "phonelines/<int:pk>/delete/",
        PhoneLineDeleteView.as_view(),
        name="phoneline_delete",
    ),
    path(
        "phonelines/<int:pk>/history/",
        PhoneLineHistoryView.as_view(),
        name="phoneline_history",
    ),
    path("simcards/create/", SIMcardCreateView.as_view(), name="simcard_create"),
    path(
        "simcards/<int:pk>/update/", SIMcardUpdateView.as_view(), name="simcard_update"
    ),
    path(
        "phonelines/<int:pk>/history/export/",
        ExportPhoneLinesCSVView.as_view(),
        name="phoneline_history_export",
    ),
]
