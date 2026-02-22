from django.urls import path

from .views import RegistrationHubView, LineAllocationReleaseView

app_name = 'allocations'

urlpatterns = [
    path('', RegistrationHubView.as_view(), name='allocation_list'),
    path('<int:pk>/release/', LineAllocationReleaseView.as_view(),
         name='allocation_release'),
]
