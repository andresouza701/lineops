from django.contrib import admin

from .models import SIMcard, PhoneLine

@admin.register(SIMcard)
class SIMcardAdmin(admin.ModelAdmin):
    list_display = ('iccid', 'carrier', 'status', 'activated_at')
    search_fields = ('iccid', 'carrier')
    list_filter = ('status', 'carrier')

@admin.register(PhoneLine)
class PhoneLineAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'sim_card', 'status', 'activated_at')
    search_fields = ('phone_number',)
    list_filter = ('status',)