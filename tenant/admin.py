from django.contrib import admin
from django_tenants.admin import TenantAdminMixin
# Register your models here.
from tenant.models import Tenant, Domain

class DomainInline(admin.TabularInline):
    model  = Domain
    max_num = 1

@admin.register(Tenant)
class TenantAdmin(TenantAdminMixin, admin.ModelAdmin):
    list_display = (
        "id", 
        "schema_name", 
        "name", 
        "stripe_customer_id", 
        "stipe_subscription_id", 
        "salonDetails", 
        "subscription_status",
        "subscription_plan",
        "subscription_end_date",
        "trial_completed",
        "trial_end_date",
        "created_on", 
        
        )
    inlines = [DomainInline]


