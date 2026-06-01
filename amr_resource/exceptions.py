
from odoo.http import Response
import json


class APIException(Exception):
    def __init__(self, code, description=None, http_status=400):
        self.code = code
        self.message = description
        self.http_status = http_status
        super().__init__(description)


def handle_exception(e):
    # custom APIException
    if isinstance(e, APIException):
        return Response(
            json.dumps({
                "error": e.code,
                "error_description": e.message,
            }),
            status=e.http_status,
            content_type="application/json"
        )

    # Odoo standard error
    return Response(
        json.dumps({
            "error": "unknown_error",
            "error_description": str(e)
        }),
        status=500,
        content_type="application/json"
    )
