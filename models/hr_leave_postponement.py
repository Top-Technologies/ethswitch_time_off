# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class HrLeavePostponement(models.Model):
    _name = 'hr.leave.postponement'
    _description = 'Annual Leave Postponement Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        default=lambda self: self.env.user.employee_id,
        tracking=True
    )

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )

    manager_id = fields.Many2one(
        'hr.employee',
        string='Immediate Supervisor',
        related='employee_id.parent_id',
        store=True,
        readonly=True
    )

    leave_type_id = fields.Many2one(
        'hr.leave.type',
        string='Leave Type',
        required=True,
        domain="[('name', 'ilike', 'Annual')]",
        tracking=True
    )

    fiscal_year = fields.Char(
        string='Fiscal Year',
        required=True,
        help="The budget / fiscal year for which the accumulated leave is being postponed (e.g. 2016/2017 EFY)."
    )

    days_to_postpone = fields.Float(
        string='Days to Postpone',
        required=True,
        tracking=True,
        help="Number of accumulated leave days to carry forward beyond normal expiration."
    )

    original_expiry_date = fields.Date(
        string='Original Expiry Date',
        required=True,
        tracking=True,
        help="The date when the hoarded leave would normally expire."
    )

    new_expiry_date = fields.Date(
        string='New Expiry Date',
        required=True,
        tracking=True,
        help="The extended date until which the postponed leave will remain valid."
    )

    reason = fields.Text(
        string='Reason for Postponement',
        required=True,
        tracking=True,
        help="Operational or personal justification for postponing the annual leave."
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Submitted'),
        ('validate', 'Approved'),
        ('refuse', 'Refused'),
    ], string='Status', default='draft', readonly=True, tracking=True, copy=False)

    approved_by_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        copy=False
    )

    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
        copy=False
    )

    allocation_id = fields.Many2one(
        'hr.leave.allocation',
        string='Resulting Allocation',
        readonly=True,
        copy=False,
        help="Allocation created to extend the validity of the postponed leave days."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.leave.postponement') or _('Postponement')
        return super().create(vals_list)

    @api.constrains('days_to_postpone', 'original_expiry_date', 'new_expiry_date')
    def _check_postponement_dates(self):
        for rec in self:
            if rec.days_to_postpone <= 0:
                raise ValidationError(_("Days to postpone must be greater than zero."))
            if rec.new_expiry_date <= rec.original_expiry_date:
                raise ValidationError(_("The New Expiry Date must be strictly after the Original Expiry Date."))

    def action_submit(self):
        self.ensure_one()
        self.write({'state': 'confirm'})
        hr_group = self.env.ref('hr_holidays.group_hr_holidays_user', raise_if_not_found=False)
        if hr_group and hr_group.users:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Annual Leave Postponement Request: %s') % self.employee_id.name,
                user_id=hr_group.users[0].id
            )

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_holidays.group_hr_holidays_user'):
            raise UserError(_("Only HR Officers / Administrators can approve Leave Postponements."))

        # Create allocation for the postponed days with the new validity date
        allocation_vals = {
            'name': _("Postponed Annual Leave (%s - %s)") % (self.employee_id.name, self.fiscal_year),
            'holiday_status_id': self.leave_type_id.id,
            'employee_id': self.employee_id.id,
            'number_of_days': self.days_to_postpone,
            'allocation_type': 'regular',
            'date_to': self.new_expiry_date,
            'notes': _("Created from approved Leave Postponement request %(ref)s. Reason: %(reason)s",
                       ref=self.name, reason=self.reason),
        }
        allocation = self.env['hr.leave.allocation'].create(allocation_vals)
        allocation.action_validate()

        self.write({
            'state': 'validate',
            'approved_by_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'allocation_id': allocation.id,
        })
        self.message_post(body=_("Leave Postponement approved by HR. New validity date: %s.") % self.new_expiry_date)

    def action_refuse(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_holidays.group_hr_holidays_user'):
            raise UserError(_("Only HR Officers / Administrators can refuse Leave Postponements."))
        self.write({'state': 'refuse'})
        self.message_post(body=_("Leave Postponement request was refused."))

    def action_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})
