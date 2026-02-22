from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import PhoneLine, SIMcard


class SIMcardListView(LoginRequiredMixin, ListView):
    model = SIMcard
    template_name = 'telecom/simcard_list.html'
    context_object_name = 'simcards'
    ordering = ['iccid']


class PhoneLineListView(LoginRequiredMixin, ListView):
    model = PhoneLine
    template_name = 'telecom/phoneline_list.html'
    context_object_name = 'phone_lines'
    ordering = ['phone_number']
