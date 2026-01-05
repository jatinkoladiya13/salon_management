
from rest_framework.views import exception_handler
from rest_framework import status
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    print("Exception::::-", str(exc))
    if response is not None:
        custom_response_data = {
            "error": True,
            "data": {},
            "message": getattr(exc, "detail", str(exc)),
        }

        # if response.status_code == 403:
        #     return Response(
        #         custom_response_data, status=status.HTTP_401_UNAUTHORIZED
        #     )
        return Response(custom_response_data, status=response.status_code)
    else:
        return Response(
            {
                "error": True,
                "data": {},
                "message": str(exc),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )