from django.urls import path

from .views import PhoneLineListView, SIMcardListView, TelecomOverviewView

app_name = 'telecom'

urlpatterns = [
    path('', TelecomOverviewView.as_view(), name='overview'),
    path('simcards/', SIMcardListView.as_view(), name='simcard_list'),
    path('phonelines/', PhoneLineListView.as_view(), name='phoneline_list'),
]
