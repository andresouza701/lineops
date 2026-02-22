from django.urls import path

from .views import LineAllocationListView

app_name = 'allocations'

urlpatterns = [
    path('', LineAllocationListView.as_view(), name='allocation_list'),
]
