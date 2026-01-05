from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
# Register your models here.
from tenant.models import Tenant, Domain

class DomainInline(admin.TabularInline):
    model  = Domain
    max_num = 1

@admin.register(Tenant)
class TenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = ("name",)
    inlines = [DomainInline]


