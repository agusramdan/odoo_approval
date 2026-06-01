# -*- coding: utf-8 -*-

class ApiException(Exception):
    status = 400
    error = "unknown_error"
    description = "Unknown error."

    def __init__(
            self,
            description=None,
            status=None,
            error=None,
    ):
        if description:
            self.description = description

        if status:
            self.status = status

        if error:
            self.error = error

        super().__init__(self.description)

    def to_dict(self):
        return {
            "success": False,
            "error": self.error,
            "error_description": self.description,
        }


class DeviceNotFoundException(ApiException):
    error = "device_not_found"
    description = "Device not found."


class ValidationException(ApiException):
    status = 400
    error = "invalid_data"


class PartnerNotFoundException(ApiException):
    status = 400
    error = "invalid_partner"
    description = "Partner is not found."


class InvalidPartnerException(ApiException):
    status = 400
    error = "invalid_partner"
    description = "Partner is invalid."


class InvalidChallengeException(ApiException):
    status = 400
    error = "invalid_challenge"
    description = "Challenge is invalid."


class ChallengeExpiredException(ApiException):
    status = 400
    error = "challenge_expired"
    description = "Challenge has expired."


class UnauthorizedException(ApiException):
    status = 401
    error = "unauthorized"
    description = "Authentication required."


class ForbiddenException(ApiException):
    status = 403
    error = "forbidden"
    description = "Access denied."


class InvalidScopeException(ApiException):
    status = 403
    error = "forbidden"
    description = "Invalid Scope"


class DeviceNotRegisteredException(ApiException):
    status = 404
    error = "device_not_registered"
    description = "Device is not registered."
