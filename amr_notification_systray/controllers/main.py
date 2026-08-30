# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class NotificationBusController(http.Controller):

    @http.route('/amr_notification_systray/notifications', type='json', auth='user', methods=['POST'], )
    def notifications(self, limit=20, offset=0, **kwargs):
        Notification = request.env['notification.partner']
        notifications = Notification.search(
            [('user_id', '=', request.env.user.id), ],
            limit=limit,
            offset=offset,
            order='create_date desc',
        )
        return {
            'notifications': [notification.notification_bus_dict() for notification in notifications],
            'unread_count': Notification.search_count([('user_id', '=', request.env.user.id), ('is_read', '=', False)]),
            'limit': limit,
            'offset': offset,
            'length': len(notifications)
        }

    @http.route('/amr_notification_systray/toggle_read', type='json', auth='user')
    def toggle_read(self, notification_id, is_read, **kwargs):
        # Cari record notifikasi berdasarkan ID, lalu perbarui field is_read-nya
        notification = request.env['notification.partner'].browse(int(notification_id))
        if notification.exists():
            notification.write({'is_read': is_read})
        return True
