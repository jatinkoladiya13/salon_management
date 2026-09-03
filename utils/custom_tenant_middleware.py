
from django.db import connection

from tenant.models import Tenant


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        original_path = request.path_info
        path_parts = original_path.strip("/").split("/")

        tenant_schema_name = path_parts[0] if path_parts else None

        if tenant_schema_name:
            try:
                tenant = Tenant.objects.get(schema_name=tenant_schema_name)
            except Tenant.DoesNotExist:
                tenant = None

            if tenant is not None:
                request.tenant = tenant
                connection.set_tenant(tenant)
                rewritten_path = original_path[len(tenant_schema_name) + 1:] or "/"
                request.path_info = rewritten_path
                request.META["PATH_INFO"] = rewritten_path

        return self.get_response(request)