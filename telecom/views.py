from core.mixins import AuthenticadView
from django.db.models import Count, Q
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
        context['total_simcards'] = SIMcard.objects.filter(is_deleted=False).count()
        base_lines = PhoneLine.objects.filter(is_deleted=False)
        context['total_lines'] = base_lines.count()
        counts = self._line_status_counts(base_lines)
        context['allocated_lines'] = LineAllocation.objects.filter(is_active=True).count()
        context['available_lines'] = counts.get(PhoneLine.Status.AVAILABLE, 0)
        context['cancelled_lines'] = counts.get(PhoneLine.Status.CANCELLED, 0)
        context['blocked_lines'] = counts.get(PhoneLine.Status.SUSPENDED, 0)

        search = self.request.GET.get('search', '').strip()
        context['search_query'] = search

        lines_qs = base_lines.select_related('sim_card').order_by('phone_number')
        if search:
            lines_qs = lines_qs.filter(
                Q(phone_number__icontains=search) |
                Q(sim_card__iccid__icontains=search)
            )
        context['phone_lines'] = lines_qs
        context.update(self._line_status_summary(counts))
        return context

    def _line_status_counts(self, queryset):
        return {
            row['status']: row['count']
            for row in queryset.values('status').annotate(count=Count('id'))
        }

    def _line_status_summary(self, counts):
        boxes = [
            {
                'value': PhoneLine.Status.AVAILABLE,
                'label': 'Disponíveis',
                'description': 'Prontas para novos colaboradores',
                'variant': 'success',
            },
            {
                'value': PhoneLine.Status.ALLOCATED,
                'label': 'Ativas',
                'description': 'Alocadas e em uso',
                'variant': 'primary',
            },
            {
                'value': PhoneLine.Status.SUSPENDED,
                'label': 'Bloqueadas',
                'description': 'Suspensas temporariamente',
                'variant': 'warning',
            },
            {
                'value': PhoneLine.Status.CANCELLED,
                'label': 'Canceladas',
                'description': 'Encerradas ou desativadas',
                'variant': 'danger',
            },
        ]

        status_boxes = []
        for box in boxes:
            status_boxes.append({
                'label': box['label'],
                'count': counts.get(box['value'], 0),
                'value': box['value'],
                'description': box['description'],
                'variant': box['variant'],
            })

        return {
            'line_status_boxes': status_boxes,
        }
