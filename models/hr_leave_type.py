# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    count_calendar_days = fields.Boolean(
        string='Count in Calendar Days',
        default=False,
        help="If checked, leave duration will be calculated strictly in consecutive calendar days (including weekends and public holidays), rather than working schedule days."
    )

    gender_restriction = fields.Selection([
        ('all', 'All Employees'),
        ('male', 'Male Only'),
        ('female', 'Female Only'),
    ], string='Gender Restriction', default='all', required=True,
       help="Restricts this leave type to employees of the selected gender (e.g. Prenatal/Postnatal for female, Paternity for male).")

    permanent_only = fields.Boolean(
        string='Permanent Employees Only',
        default=False,
        help="If checked, only permanent employees (Contract / Employee Type: 'Permanent') are eligible to request this leave type."
    )

    fixed_duration = fields.Float(
        string='Fixed Duration (Days)',
        default=0.0,
        help="If greater than 0, any request for this leave type will automatically enforce this exact duration in days (e.g., 30 days for Prenatal, 90 days for Postnatal)."
    )

    max_duration_per_request = fields.Float(
        string='Maximum Duration per Request (Days)',
        default=0.0,
        help="If greater than 0, a single leave request cannot exceed this number of days (e.g., 3 days for Wedding, Mourning, Paternity)."
    )

    deduct_from_type_id = fields.Many2one(
        'hr.leave.type',
        string='Deduct Balance From',
        domain="[('id', '!=', id)]",
        help="If set, leaves requested under this type will draw down the allocated balance of the selected leave type (e.g. Leave of Absence deducting from Annual Leave)."
    )

    require_zero_annual_balance = fields.Boolean(
        string='Require Nil Annual Leave Balance',
        default=False,
        help="If checked, an employee can only request this leave type if their remaining Annual Leave balance is 0 or less (e.g. Leave Without Pay)."
    )

    @api.constrains('fixed_duration', 'max_duration_per_request')
    def _check_durations(self):
        for record in self:
            if record.fixed_duration < 0 or record.max_duration_per_request < 0:
                raise ValidationError(_("Duration limits cannot be negative."))
