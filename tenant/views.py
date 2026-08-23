from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from tenant.models import Tenant, Domain

from subscription.models import SubscriptionPlan
from salonDetails.models import SalonDetails

from utils.custom_exception import BadRequestException
from utils.permissions import IsPublicSchemaSuperUser

from .serializers import *

import utils.response_handler as rh
import datetime


TRIAL_PERIOD_DAYS = 7


# Create your views here.
def create_tenant_and_domain(tenant_name, domain_name, salonDetails):
    salon = SalonDetails.objects.filter(id=salonDetails).first()
    if salon is None:
        raise BadRequestException("Salon details not found for this workspace.")

    subscription_plan = SubscriptionPlan.objects.filter(
        plan_type="free", interval="trial"
    ).first()
    if subscription_plan is None:
        # Without the free trial plan seeded there is nothing to put a new
        # workspace on; fail loudly here instead of half-creating a tenant.
        raise BadRequestException(
            "No trial subscription plan is configured. Please contact support."
        )

    tenant = Tenant(
        name=tenant_name,
        schema_name=tenant_name,
        salonDetails=salon,
    )
    tenant.auto_create_schema = False

    tenant.subscription_plan_id = subscription_plan.id
    tenant.subscription_status = "active"
    tenant.subscription_end_date = timezone.now() + datetime.timedelta(
        days=TRIAL_PERIOD_DAYS
    )

    # The tenant row, its domain and its schema have to appear together - a
    # tenant whose schema creation failed is unusable but still blocks the slug.
    with transaction.atomic():
        tenant.save()

        domain = Domain(tenant=tenant, domain=domain_name, is_primary=True)
        domain.save()

        call_command("create_new_schema", tenant.schema_name)
    # call_command("role_base_permissions", tenant.schema_name)
    # call_command("create_tenantadmin_group", tenant.schema_name)
    # call_command("create_staff_group", tenant.schema_name)
    # call_command("create_user_group", tenant.schema_name)
    return tenant

class TenantViewSet(ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TeantSerializer
    permission_classes = [IsPublicSchemaSuperUser]
   
    @action(detail=False, methods=['get'], url_path='get-tenant')
    def get_tenant(self, request):
        salon_id = request.query_params.get('salon_id')

        if not salon_id:
            response = rh.ResponseMsg(
                data={},
                error=True,
                msg="Salon id is required.",
            )
            return Response(response.response, status=status.HTTP_400_BAD_REQUEST)

        tenants = Tenant.objects.filter(salonDetails_id=salon_id)

        serializer_data = self.serializer_class(tenants, many=True).data
        response = rh.ResponseMsg(
             data=serializer_data,
            error=False,
            msg="Tenant Details Get Successfully",
        )

        return Response(response.response, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='create-tenant')
    def create_tenant(self, request, *args, **kwargs):

        serializer = TenantDomainSerializer(data=request.data)
        if serializer.is_valid():
            tenant_name = serializer.validated_data["tenant_name"]
            domain_name = serializer.validated_data["domain_name"]
            salon_id = serializer.validated_data["salon"]

            if (
                Tenant.objects.filter(name=tenant_name).exists()
                or Tenant.objects.filter(schema_name=tenant_name).exists()
            ):
                return Response(
                    {"error":"Tenant with this name already exists."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if Domain.objects.filter(domain = domain_name).exists():
                return Response(
                    {"error":"Domian with this name already exists."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if Tenant.objects.filter(salonDetails_id=salon_id).exists():
                return Response(
                    {"error":"Tenant with this salon already exists."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            
            # Create tenant amnd domain
            create_tenant_and_domain(tenant_name, domain_name, salon_id)

            response = rh.ResponseMsg(
                data=serializer.data,
                error=False,
                msg="Tenant created successfully",
            )
            return Response(response.response, status=status.HTTP_201_CREATED)

        response = rh.ResponseMsg(
            data=serializer.errors, error=True, msg="Error Creating Tenant"
        )
        return Response(response.response, status=status.HTTP_400_BAD_REQUEST)
    
    def _rename_primary_domain(self, tenant, new_domain, serializer):
        if tenant is None:
            response = rh.ResponseMsg(
                data={}, error=True, msg="Tenant not found."
            )
            return Response(response.response, status=status.HTTP_404_NOT_FOUND)

        domain = (
            Domain.objects.filter(tenant=tenant)
            .order_by("-is_primary", "id")
            .first()
        )
        if domain is None:
            response = rh.ResponseMsg(
                data={}, error=True, msg="This tenant has no domain to update."
            )
            return Response(response.response, status=status.HTTP_404_NOT_FOUND)

        if (
            Domain.objects.filter(domain=new_domain)
            .exclude(pk=domain.pk)
            .exists()
        ):
            response = rh.ResponseMsg(
                data={}, error=True, msg="Domain with this name already exists."
            )
            return Response(response.response, status=status.HTTP_400_BAD_REQUEST)

        domain.domain = new_domain
        domain.save(update_fields=["domain"])

        response = rh.ResponseMsg(
            data=serializer.data,
            error=False,
            msg="Domain updated successfully",
        )
        return Response(response.response, status=status.HTTP_200_OK)

    @action(detail=True, methods=['put', 'patch'], url_path='update-domain')
    def update_domain(self, request, pk=None):
        serializer = UpdateDomainSerializer(data=request.data)
        # Every branch has to return a response - falling off the end of the
        # method made Django raise "view didn't return an HttpResponse".
        serializer.is_valid(raise_exception=True)

        return self._rename_primary_domain(
            Tenant.objects.filter(id=pk).first(),
            serializer.validated_data["domain_name"],
            serializer,
        )

    @action(detail=True, methods=['put', 'patch'], url_path='update-domain-by-salon')
    def update_domain_by_customer(self, request, pk):
        serializer = UpdateDomainSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        return self._rename_primary_domain(
            Tenant.objects.filter(salonDetails_id=pk).first(),
            serializer.validated_data["domain_name"],
            serializer,
        )

