from django.urls import path

from .views import DashboardView

urlspatterns = [
    path("", DashboardView.as_view(), name='dashboard'),
]