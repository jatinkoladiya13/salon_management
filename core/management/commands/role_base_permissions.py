from django.core.management.base import BaseCommand
from core.models import RoleBasePermissions
from core.constants import *
from django_tenants.utils import get_tenant_model

PERMISSIONS = [
    # ========== Group Permissions ==========
    {
        "name": READ_GROUPS,
        "text": "For viewing all groups",
    },
    {
        "name": CREATE_GROUPS,
        "text": "For creating a new group",
    },
    {
        "name": UPDATE_GROUPS,
        "text": "For updating group details",
    },
    {
        "name": DELETE_GROUPS,
        "text": "For deleting a group",
    },

    # ========== Permission Status ==========
    {
        "name": READ_PERMISSIONS_STATUS,
        "text": "For viewing permission status",
    },
    {
        "name": UPDATE_PERMISSIONS_STATUS,
        "text": "For updating permission status",
    },

    # ========== User Permissions ==========
    {
        "name": READ_USERS_ACCOUNT,
        "text": "For viewing all user accounts",
    },
    {
        "name": CREATE_USERS_ACCOUNT,
        "text": "For creating a new user account",
    },
    {
        "name": UPDATE_USERS_ACCOUNT,
        "text": "For updating user account details",
    },
    {
        "name": DELETE_USERS_ACCOUNT,
        "text": "For deleting a user account",
    },
    {
        "name": CREATE_OWN_ACCOUNT_ONLY,
        "text": "For creating only the user's own account",
    },
    {
        "name": READ_OWN_ACCOUNT_ONLY,
        "text": "For viewing only the user's own account",
    },
    {
        "name": UPDATE_OWN_ACCOUNT_ONLY,
        "text": "For updating only the user's own account",
    },
    {
        "name": DELETE_OWN_ACCOUNT_ONLY,
        "text": "For deleting only the user's own account",
    },

    # ========== Salon Details Permissions ==========
    {
        "name": READ_SALON_DETAILS,
        "text": "For viewing salon details",
    },
    {
        "name": CREATE_SALON_DETAILS,
        "text": "For creating salon details",
    },
    {
        "name": UPDATE_SALON_DETAILS,
        "text": "For updating salon details",
    },
    {
        "name": DELETE_SALON_DETAILS,
        "text": "For deleting salon details",
    },

    # ========== Service Permissions ==========
    {
        "name": READ_SERVICES,
        "text": "For viewing all services",
    },
    {
        "name": CREATE_SERVICES,
        "text": "For creating a new service",
    },
    {
        "name": UPDATE_SERVICES,
        "text": "For updating service details",
    },
    {
        "name": DELETE_SERVICES,
        "text": "For deleting a service",
    },

    # ========== Staff Services Permissions ==========
    {
        "name": READ_STAFF_SERVICES,
        "text": "For viewing staff services",
    },
    {
        "name": CREATE_STAFF_SERVICES,
        "text": "For assigning services to staff",
    },
    {
        "name": UPDATE_STAFF_SERVICES,
        "text": "For updating staff service assignments",
    },
    {
        "name": DELETE_STAFF_SERVICES,
        "text": "For removing services assigned to staff",
    },

    # ========== Appointment Permissions ==========
    {
        "name": READ_APPOINTMENTS,
        "text": "For viewing all appointments",
    },
    {
        "name": CREATE_APPOINTMENTS,
        "text": "For creating a new appointment",
    },
    {
        "name": UPDATE_APPOINTMENTS,
        "text": "For updating appointment details",
    },
    {
        "name": DELETE_APPOINTMENTS,
        "text": "For deleting an appointment",
    },

    # ========== Time Slot Permissions ==========
    {
        "name": READ_TIME_SLOTS,
        "text": "For viewing all time slots",
    },
    {
        "name": CREATE_TIME_SLOTS,
        "text": "For creating a new time slot",
    },
    {
        "name": UPDATE_TIME_SLOTS,
        "text": "For updating time slot details",
    },
    {
        "name": DELETE_TIME_SLOTS,
        "text": "For deleting a time slot",
    },

    # ========== Product Category Permissions ==========
    {
        "name": READ_PRODUCT_CATEGORIES,
        "text": "For viewing all product categories",
    },
    {
        "name": CREATE_PRODUCT_CATEGORIES,
        "text": "For creating a new product category",
    },
    {
        "name": UPDATE_PRODUCT_CATEGORIES,
        "text": "For updating product category details",
    },
    {
        "name": DELETE_PRODUCT_CATEGORIES,
        "text": "For deleting a product category",
    },

    # ========== Product Permissions ==========
    {
        "name": READ_PRODUCTS,
        "text": "For viewing all products",
    },
    {
        "name": CREATE_PRODUCTS,
        "text": "For creating a new product",
    },
    {
        "name": UPDATE_PRODUCTS,
        "text": "For updating product details",
    },
    {
        "name": DELETE_PRODUCTS,
        "text": "For deleting a product",
    },

    # ========== Invoice Management Permissions ==========
    {
        "name": READ_INVOICES,
        "text": "For viewing all invoices",
    },
    {
        "name": CREATE_INVOICES,
        "text": "For creating a new invoice",
    },
    {
        "name": UPDATE_INVOICES,
        "text": "For updating invoice details",
    },
    {
        "name": DELETE_INVOICES,
        "text": "For deleting an invoice",
    },

    # ========== Stock Management Permissions ==========
    {
        "name": READ_STOCKS,
        "text": "For viewing all stock records",
    },
    {
        "name": CREATE_STOCKS,
        "text": "For creating a new stock record",
    },
    {
        "name": UPDATE_STOCKS,
        "text": "For updating stock details",
    },
    {
        "name": DELETE_STOCKS,
        "text": "For deleting a stock record",
    },
]

class Command(BaseCommand):
    help = "Create permissions"

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name", type=str, nargs="?", help="schema name"
        )

    def obj_created(self):
        for permission in PERMISSIONS:
            (   
                permission_obj,
                created,
            ) = RoleBasePermissions.objects.get_or_create(
                name = permission["name"]
            )
            permission_obj.description = permission["text"]
            permission_obj.save()

    def handle(self, *args, **options):
        schema_name = options["schema_name"]

        if not schema_name:
            schema_name = input("Enter Tenant Schema ('?' to list schemas): ")

        Tenant = get_tenant_model()

        try:
            tenant = Tenant.objects.get(schema_name=schema_name)
            with tenant:
                self.obj_created()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created default Permissions for tenant {schema_name}"
                    )
                ) 
        except Tenant.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f"Tenant with schema name {schema_name} does not exist"
                )
            )           

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Error in Created default Permissions :- {str(e)}"
                )
            )       


