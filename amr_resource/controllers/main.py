# -*- coding: utf-8 -*-

from werkzeug.utils import redirect
from odoo.http import Controller, request, route


class RedirectController(Controller):

    @route(['/redirect'], type='http', auth='user_or_param', methods=['GET'], csrf=False)
    def redirect_url(self, url=None):
        url = request.env.user.add_url_access_token(url)
        return redirect(url)
