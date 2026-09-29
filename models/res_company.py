# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    fiscal_year_start_month = fields.Selection([
        ('1', 'January'),
        ('2', 'February'),
        ('3', 'March'),
        ('4', 'April'),
        ('5', 'May'),
        ('6', 'June'),
        ('7', 'July'),
        ('8', 'August'),
        ('9', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
    ], string='Fiscal Year Start Month', default='7',
       help="Month when the fiscal/budget year begins (default July for Ethiopian Fiscal Year).")

    fiscal_year_start_day = fields.Integer(
        string='Fiscal Year Start Day', default=8,
        help="Day of month when fiscal year starts (e.g., 8th of July corresponds to Hamle 1).")

    leave_encashment_divisor = fields.Float(
        string='Daily Wage Divisor', default=26.0,
        help="Divisor applied to monthly basic salary to determine daily wage for leave encashment and settlements (typically 26 working days or 30 calendar days).")

    leave_expiry_warning_days = fields.Integer(
        string='Leave Expiry Warning (Days)', default=30,
        help="Number of days before the end of the two-year accumulation cycle to notify employees and supervisors about expiring leave.")
