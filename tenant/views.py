from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from django.core.management import call_command
from django.shortcuts import render

from tenant.models import Tenant, Domain

from subscription.models import SubscriptionPlan
from salonDetails.models import SalonDetails

from utils.permissions import IsPublicSchemaSuperUser

from .serializers import *

import utils.response_handler as rh
import datetime


# Create your views here.
def create_tenant_and_domain(tenant_name, domain_name, salonDetails):
    tenant = Tenant(
        name = tenant_name,
        schema_name = tenant_name,
        salonDetails = SalonDetails.objects.get(id=salonDetails) 
    )
    tenant.auto_create_schema = False

    print("tenant_name:", tenant_name)
    subscription_plan = SubscriptionPlan.objects.get(
        plan_type="free", interval="trial"
    )

    print("subscription_plan:", subscription_plan)

    tenant.subscription_plan_id = subscription_plan.id
    tenant.subscription_status = "active"
    tenant.subscription_end_date = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(days=7)
    tenant.save()
    
    domain = Domain(tenant=tenant, domain=domain_name)
    domain.save()

    print("Tenant and Domain created successfully.")
    print("schema_name:", tenant.schema_name)

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

            if Tenant.objects.filter(name=tenant_name).exists():
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
    
    @action(detail=True, methods=['put', 'patch'], url_path='update-domain')
    def update_domain(self, request, pk=None):
        
        serializer = UpdateDomainSerializer(data=request.data)
        if serializer.is_valid():
            tenant = Tenant.objects.get(id=pk)
            domain = Domain.objects.get(tenant=tenant)
            domain.domain = request.data.get("domain_name")
            domain.save()

            response = rh.ResponseMsg(
                data=serializer.data,
                error= False,
                msg="Domain updated successfully"
            )
            return Response(response.response, status=status.HTTP_200_OK)
        
    @action(detail=True, methods=['put', 'patch'], url_path='update-domain-by-salon')    
    def update_domain_by_customer(self, request, pk):
        serializer = UpdateDomainSerializer(data=request.data)
        if serializer.is_valid():
            print("serializer.validated_data", serializer.validated_data)
            tenant = Tenant.objects.filter(
                salonDetails_id=pk
            )
            domain = Domain.objects.get(tenant=tenant[0])
            domain.domain = request.data.get("domain_name")
            domain.save()
            response = rh.ResponseMsg(
                data=serializer.data,
                error=False,
                msg="Domain Updated Successfully",
            )
            return Response(response.response, status=status.HTTP_200_OK)
    
