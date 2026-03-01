from django.contrib import admin
from django.db import connection
from django_tenants.admin import TenantAdminMixin
from django_tenants.utils import schema_context
from tenant.models import Tenant
from .models import CallCredit


# Register your models here.

admin.site.register(CallCredit)

# class PublicCallCreditProxy(CallCredit):
#     class Meta:
#         proxy = True
#         verbose_name = "Tenant Call Credit"
#         verbose_name_plural = "Tenant Call Credits"

# @admin.register(PublicCallCreditProxy)
# class PublicCallCreditProxiyAdmin(admin.ModelAdmin):
#     list_display = ("credits_sec","get_queryset", "credit_type",  "expiry_date", "created_on", "expired")

#     def get_queryset(self, request):
#         qs  = CallCredit.objects.none()
#         for tenant in Tenant.objects.all():
#             with schema_context(tenant.schema_name):
#                 qs |= CallCredit.objects.all()
#         return qs        

    # def has_module_permission(self, request):
    #     return connection.schema_name != "public" 

    # def get_tenant(self, obj):
    #     return obj.tenant
    
    # get_tenant.short_description = "Tenant"