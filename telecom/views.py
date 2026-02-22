from core.mixins import AuthenticadView
from django.db.models import Count
from django.views.generic import ListView, TemplateView

from allocations.models import LineAllocation
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


class TelecomOverviewView(AuthenticadView, TemplateView):
    template_name = 'telecom/overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_simcards'] = SIMcard.objects.filter(
            is_deleted=False).count()
        context['total_lines'] = PhoneLine.objects.filter(
            is_deleted=False).count()
        context['allocated_lines'] = LineAllocation.objects.filter(
            is_active=True).count()
        context['available_lines'] = context['total_lines'] - \
            context['allocated_lines']
        context.update(self._status_counts())
        return context

    def _status_counts(self):
        sim_counts = {row['status']: row['count'] for row in SIMcard.objects.filter(is_deleted=False)
                      .values('status').annotate(count=Count('id'))}
        line_counts = {row['status']: row['count'] for row in PhoneLine.objects.filter(is_deleted=False)
                       .values('status').annotate(count=Count('id'))}

        return {
            'sim_status_counts': [
                {'label': label, 'count': sim_counts.get(value, 0)}
                for value, label in SIMcard.Status.choices
            ],
            'line_status_counts': [
                {'label': label, 'count': line_counts.get(value, 0)}
                for value, label in PhoneLine.Status.choices
            ]
        }
