from core.mixins import AuthenticadView
from django.views.generic import ListView

from .models import PhoneLine, SIMcard


class SIMcardListView(AuthenticadView, ListView):
    model = SIMcard
    template_name = 'telecom/simcard_list.html'
    context_object_name = 'simcards'
    ordering = ['iccid']


class PhoneLineListView(AuthenticadView, ListView):
    model = PhoneLine
    template_name = 'telecom/phoneline_list.html'
    context_object_name = 'phone_lines'
    ordering = ['phone_number']
