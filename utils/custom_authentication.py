from rest_framework_simplejwt import authentication, exceptions

from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from tenant.models import Tenant

class CustomJWTAuthentication(authentication.JWTAuthentication):
    def check_schema_name(self, payload, schema_name):
        try:
            payload_schema_name = payload["schema_name"]
        except KeyError:
            raise exceptions.InvalidToken(
                _("Token contained not recognizable user identification")
            ) 

        if payload_schema_name != schema_name:
            raise exceptions.InvalidToken(
                _("Token is invalid"), code="token_not_valid"
            )
        
        try:

            tenant = Tenant.objects.select_related(
                "subscription_plan"
            ).get(
                schema_name=payload_schema_name
            )

        except Tenant.DoesNotExist:
            raise  exceptions.InvalidToken(_("Invalid schema_name"))
        
        if schema_name  != "public":
            # Check subscription plan
            if not tenant.subscription_plan:
                raise exceptions.AuthenticationFailed(
                    _("No subscription plan found. Please subscribe.")
                )

            # Check subscription status
            if tenant.subscription_status != "active":
                raise exceptions.AuthenticationFailed(
                    _("Subscription is not active.")
                )
            
            if (
                tenant.subscription_end_date
                and tenant.subscription_end_date < timezone.now()
            ):
                raise exceptions.AuthenticationFailed(
                    _("Subscription has expired.")
                )

        return schema_name

    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)

        self.check_schema_name(
            validated_token.payload, request.tenant.schema_name
        )

        return self.get_user(validated_token), validated_token
    


# TODO This code schema_name required only in login api. then logied user don't required pass the schema_name in token. So, I have commented the below code. If you want to use this code then uncomment it and use it.
# TODO If you want to use this code first user know the schema_name and then pass the schema_name in token. If you don't want to use this code then remove the below code.
# from django.db import connection
# from rest_framework_simplejwt import authentication, exceptions

# from rest_framework.exceptions import AuthenticationFailed

# from django.utils.translation import gettext_lazy as _



# from tenant.models import Tenant



# class CustomJWTAuthentication(authentication.JWTAuthentication):

#     def check_schema_name(self, payload, schema_name):

#         try:

#             payload_schema_name = payload["schema_name"]

#         except KeyError:

#             raise exceptions.InvalidToken(

#                 _("Token contained not recognizable user identification")

#             ) 



#         if  schema_name != "public":

#             raise exceptions.InvalidToken(

#                 _("Token is invalid"), code="token_not_valid"

#             )



#         return schema_name



#     def authenticate(self, request):



#         header = self.get_header(request)

#         if header is None:

#             return None

    

#         raw_token = self.get_raw_token(header)

#         if raw_token is None:

#             return None



#         validated_token = self.get_validated_token(raw_token)



#         self.check_schema_name(

#             validated_token.payload, request.tenant.schema_name

#         )



#         payload_schema_name = validated_token.payload.get("schema_name")

        

        # try:

        #     tenant = Tenant.objects.get(schema_name=payload_schema_name)

        # except Tenant.DoesNotExist:

        #     raise AuthenticationFailed("Invalid schema_name")

        

#         if tenant:

#             connection.set_tenant(tenant)

#             request.tenant = tenant

    

#         return self.get_user(validated_token), validated_token
