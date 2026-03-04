from django.urls import path

from .views import (
    DashboardView,
    daily_indicator_detail,
    daily_indicator_edit,
    daily_indicator_entry,
    daily_indicator_management,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("indicadores/novo/", daily_indicator_entry, name="daily_indicator_entry"),
    path("indicadores/", daily_indicator_management, name="daily_indicator_management"),
    path(
        "indicadores/<int:pk>/", daily_indicator_detail, name="daily_indicator_detail"
    ),
    path(
        "indicadores/<int:pk>/editar/",
        daily_indicator_edit,
        name="daily_indicator_edit",
    ),
]
