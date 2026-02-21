from django.contrib import admin

from .models import LineAllocation


@admin.register(LineAllocation)
class LineAllocationAdmin(admin.ModelAdmin):
    list_display = (
        'employee',
        'phone_line',
        'allocated_at',
        'released_at',
        'is_active',
    )
    list_filter = ('is_active', 'allocated_at')
    search_fields = ('employee__full_name', 'phone_line__phone_number')
