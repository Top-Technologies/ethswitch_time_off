# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    fiscal_year_start_month = fields.Selection(
        related='company_id.fiscal_year_start_month',
        readonly=False,
        string='Fiscal Year Start Month'
    )
    fiscal_year_start_day = fields.Integer(
        related='company_id.fiscal_year_start_day',
        readonly=False,
        string='Fiscal Year Start Day'
    )
    leave_encashment_divisor = fields.Float(
        related='company_id.leave_encashment_divisor',
        readonly=False,
        string='Leave Encashment Daily Divisor'
    )
    leave_expiry_warning_days = fields.Integer(
        related='company_id.leave_expiry_warning_days',
        readonly=False,
        string='Leave Expiry Warning Notice (Days)'
    )
