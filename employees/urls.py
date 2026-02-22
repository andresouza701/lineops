from django.urls import path

from .views import (
    EmployeeCreateView,
    EmployeeDeactivateView,
    EmployeeListView,
    EmployeeUpdateView,
    EmployeeDetailView,
)

app_name = 'employees'

urlpatterns = [
    path('', EmployeeListView.as_view(), name='employee_list'),
    path('create/', EmployeeCreateView.as_view(), name='employee_create'),
    path('<int:pk>/edit/', EmployeeUpdateView.as_view(), name='employee_update'),
    path('<int:pk>/delete/', EmployeeDeactivateView.as_view(),
         name='employee_deactivate'),
    path('<int:pk>/', EmployeeDetailView.as_view(), name='employee_detail'),
]
    