from django.urls import path

from .views import LineAllocationListView

urlpatterns = [
    path('', LineAllocationListView.as_view(), name='allocation_list'),
]
