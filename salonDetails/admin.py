from django.contrib import admin
from salonDetails.models import SalonDetails, SalonOpeingHour
# Register your models here.

@admin.register(SalonDetails)
class SalonDetailsAdmin(admin.ModelAdmin):
    list_display = ('id', 'name',)


admin.site.register(SalonOpeingHour)