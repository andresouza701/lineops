from django.urls import path

from .views import (
    DashboardView,
    daily_indicator_day_breakdown,
    daily_indicator_legacy_redirect,
    daily_indicators_live,
    daily_user_action_board,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path(
        "indicadores/acoes-dia/",
        daily_user_action_board,
        name="daily_user_action_board",
    ),
    path("indicadores/live/", daily_indicators_live, name="daily_indicators_live"),
    path(
        "indicadores/dia/<str:day>/",
        daily_indicator_day_breakdown,
        name="daily_indicator_day_breakdown",
    ),
    path(
        "indicadores/novo/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_entry",
    ),
    path(
        "indicadores/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_management",
    ),
    path(
        "indicadores/<int:pk>/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_detail",
    ),
    path(
        "indicadores/<int:pk>/editar/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_edit",
    ),
    # Alias de compatibilidade para acesso via /dashboard/indicadores/...
    path(
        "dashboard/indicadores/novo/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_entry_alias",
    ),
    path(
        "dashboard/indicadores/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_management_alias",
    ),
    path(
        "dashboard/indicadores/<int:pk>/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_detail_alias",
    ),
    path(
        "dashboard/indicadores/<int:pk>/editar/",
        daily_indicator_legacy_redirect,
        name="daily_indicator_edit_alias",
    ),
]
