# -*- coding: utf-8 -*-
import json
import os

import firebase_admin

from odoo import api, models
from firebase_admin import messaging, credentials
from ..exceptions.firebase_exception import FirebaseConfigurationException, FirebaseDeliveryException
INVALID_TOKEN_ERRORS = (
    "UNREGISTERED",
    "INVALID_ARGUMENT",
)


class FirebaseService(models.AbstractModel):
    _name = "amr.firebase.service"

    @api.model
    def _load_credentials_from_file(self):

        file_path = os.getenv("AMR_NOTIFICATION_FIREBASE_CREDENTIALS_FILE")

        if not file_path:
            return None

        with open(file_path, "r") as fp:
            return json.load(fp)

    @api.model
    def _load_credentials_from_env(self):

        value = os.getenv("AMR_NOTIFICATION_FIREBASE_CREDENTIALS_JSON")

        if not value:
            return None

        return json.loads(value)

    @api.model
    def _load_credentials_from_config(self):

        value = self.env["ir.config_parameter"].sudo().get_param(
            "amr_firebase.firebase_credentials_json"
        )

        if not value:
            return None

        return json.loads(value)

    @api.model
    def _load_credentials(self):

        return (
                self._load_credentials_from_file()
                or self._load_credentials_from_env()
                or self._load_credentials_from_config()
                or self._raise_missing_credentials()
        )

    @api.model
    def _raise_missing_credentials(self):
        raise FirebaseConfigurationException(
            "Firebase credential not configured."
        )

    @api.model
    def _validate_credentials(self, credential_dict, ):

        required = [
            "project_id",
            "private_key",
            "client_email",
        ]

        for field in required:

            if not credential_dict.get(field):
                raise FirebaseConfigurationException("%s missing" % field)

    @api.model
    def _get_firebase_app(self):

        try:
            return firebase_admin.get_app()

        except ValueError:
            pass

        try:
            credential_dict = self._load_credentials()
            credential = credentials.Certificate(
                credential_dict,
            )

            return firebase_admin.initialize_app(
                credential,
            )

        except ValueError:
            return firebase_admin.get_app()

    @api.model
    def _normalize_data(self, data, **kwargs):
        result = {}

        for key, value in (data or {}).items():
            result[str(key)] = str(value)

        return result

    @api.model
    def _prepare_topic_message(self, topic, title, body, data=None, **kwargs):
        message = messaging.Message(
            topic=topic,
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=self._normalize_data(data, **kwargs),
            **kwargs
        )
        return message

    @api.model
    def send_to_topic(self, topic, title, body, data=None):
        message = self._prepare_topic_message(topic, title, body, data=data)
        return messaging.send(message, app=self._get_firebase_app(), )

    @api.model
    def _prepare_tokens_multicast(self, tokens, title, body, data=None, **kwargs):
        multicast = messaging.MulticastMessage(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=self._normalize_data(data, **kwargs),
            tokens=tokens,
            **kwargs
        )
        return multicast

    @api.model
    def send_to_tokens(self, tokens, title, body, data=None):
        if not tokens:
            return []
        android = messaging.AndroidConfig(
            priority='high',
            ttl=3600,
            collapse_key="update",
        )
        apns = messaging.APNSConfig(
            headers={
                "apns-priority": "10",
            },
            payload=messaging.APNSPayload(
                aps=messaging.Aps(
                    sound="default",
                    content_available=True,
                ),
            ),
        )
        multicast = self._prepare_tokens_multicast(tokens, title, body, data=data, android=android, apns=apns, )
        response = messaging.send_each_for_multicast(multicast, app=self._get_firebase_app(), )
        return self._parse_multicast_response(tokens, response, )

    @api.model
    def _parse_multicast_response(self, tokens, response, ):
        results = []
        for token, item in zip(tokens, response.responses, ):

            if item.success:
                results.append({
                    "token": token,
                    "success": True,
                    "message_id": item.message_id,
                })
            else:
                results.append({
                    "token": token,
                    "success": False,
                    "error": self._firebase_error_code(item.exception, ),
                })

        return results

    @api.model
    def _firebase_error_code(self, exception, ):
        if not exception:
            return None

        return getattr(
            exception,
            "code",
            "UNKNOWN",
        )
