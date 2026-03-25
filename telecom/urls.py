from django.urls import include, path

from .views import (
    BlipConfigurationCreateView,
    BlipConfigurationListView,
    BlipConfigurationUpdateView,
    ExportPhoneLinesCSVView,
    PhoneLineCreateView,
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
    path(
        "phonelines/create/",
        PhoneLineCreateView.as_view(),
        name="phoneline_create",  # noqa: E501
    ),
    path(
        "phonelines/<int:pk>/",
        PhoneLineDetailView.as_view(),
        name="phoneline_detail",  # noqa: E501
    ),
    path(
        "phonelines/<int:pk>/update/",
        PhoneLineUpdateView.as_view(),
        name="phoneline_update",  # noqa: E501
    ),
    path(
        "phonelines/<int:pk>/delete/",
        PhoneLineDeleteView.as_view(),
        name="phoneline_delete",  # noqa: E501
    ),
    path(
        "phonelines/<int:pk>/history/",
        PhoneLineHistoryView.as_view(),
        name="phoneline_history",  # noqa: E501
    ),
    path(
        "simcards/create/", SIMcardCreateView.as_view(), name="simcard_create"
    ),  # noqa: E501
    path(
        "simcards/<int:pk>/update/",
        SIMcardUpdateView.as_view(),
        name="simcard_update",  # noqa: E501
    ),
    path(
        "phonelines/<int:pk>/history/export/",
        ExportPhoneLinesCSVView.as_view(),
        name="phoneline_history_export",  # noqa: E501
    ),
    path(
        "phonelines/<int:line_pk>/whatsapp/",
        include(("whatsapp.urls", "whatsapp"), namespace="whatsapp"),
    ),
]
