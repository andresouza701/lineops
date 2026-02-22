from django.urls import path

from .views import (
    PhoneLineListView,
    SIMcardListView,
    TelecomOverviewView,
    PhoneLineDeleteView,
    PhoneLineCreateView,
    PhoneLineUpdateView,
    PhoneLineDetailView,
)

app_name = 'telecom'

urlpatterns = [
    path('', TelecomOverviewView.as_view(), name='overview'),
    path('simcards/', SIMcardListView.as_view(), name='simcard_list'),
    path('phonelines/', PhoneLineListView.as_view(), name='phoneline_list'),
    path('phonelines/create/', PhoneLineCreateView.as_view(),
         name='phoneline_create'),
    path('phonelines/<int:pk>/', PhoneLineDetailView.as_view(),
         name='phoneline_detail'),
    path('phonelines/<int:pk>/update/', PhoneLineUpdateView.as_view(),
         name='phoneline_update'),
    path('phonelines/<int:pk>/delete/', PhoneLineDeleteView.as_view(),
         name='phoneline_delete'),
]
