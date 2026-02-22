from core.mixins import AuthenticadView
from django.views.generic import ListView

from .models import LineAllocation


class LineAllocationListView(AuthenticadView, ListView):
    model = LineAllocation
    template_name = 'allocations/allocation_list.html'
    context_object_name = 'allocations'
    ordering = ['-allocated_at']
    queryset = LineAllocation.objects.select_related('employee', 'phone_line')
