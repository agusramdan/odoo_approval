# -*- coding: utf-8 -*-

from odoo import models


class NotificationTopic(models.Model):
    _inherit = "notification.topic"

    def send_to_topic(self):
        self.env["amr.firebase.service"].send_to_topic(
            topic=self.topic,
            title=self.title,
            body=self.body,
            image=self.image,
            data=self._get_data_payload(),
        )
