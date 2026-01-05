from django.shortcuts import render
from tenant.models import Tenant, Domain
from subscription.models import SubscriptionPlan
from django.core.management import call_command
from salonDetails.models import SalonDetails
import datetime

# Create your views here.
def create_tenant_and_domain(tenant_name, domain_name, salonDetails):
    tenant = Tenant(
        name = tenant_name,
        schema_name = tenant_name,
        salonDetails = SalonDetails.objects.get(id=salonDetails) 
    )

    subscription_plan = SubscriptionPlan.objects.get(
        slug="trial_subscription", interval="trial"
    )

    tenant.subscription_plan_id = subscription_plan.id
    tenant.subscription_status = "active"
    tenant.trial_completed = True
    tenant.subscription_end_date = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(days=7)
    tenant.save()
    
    domain = Domain(tenant=tenant, domain=domain_name)
    domain.save()

    # call_command("role_base_permissions", tenant.schema_name)
    # call_command("create_superadmin_group", tenant.schema_name)
    call_command("create_new_schema", tenant.schema_name)
    return tenant