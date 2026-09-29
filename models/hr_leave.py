# -*- coding: utf-8 -*-
from datetime import timedelta
import math
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    presumed_delivery_date = fields.Date(
        string='Presumed Delivery Date',
        tracking=True,
        help="Expected delivery date for prenatal maternity leave."
    )

    actual_delivery_date = fields.Date(
        string='Actual Delivery Date',
        tracking=True,
        help="Date of delivery for postnatal maternity leave."
    )

    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True,
        copy=False,
        tracking=True,
        help="Timestamp when the leave was approved by the supervisor or HR."
    )

    schedule_line_id = fields.Many2one(
        'hr.leave.schedule.line',
        string='Schedule Line',
        readonly=True,
        copy=False,
        help="Reference to the approved annual leave schedule line if booked via schedule."
    )

    is_calendar_days = fields.Boolean(
        related='holiday_status_id.count_calendar_days',
        string='Counted in Calendar Days',
        readonly=True
    )

    can_reverse_by_manager = fields.Boolean(
        string='Can Manager Reverse',
        compute='_compute_can_reverse_by_manager',
        help="Indicates whether the current user (supervisor) is within the 5-day reversal window."
    )

    @api.depends('approval_date')
    def _compute_can_reverse_by_manager(self):
        is_hr_user = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
        now = fields.Datetime.now()
        for leave in self:
            if is_hr_user:
                leave.can_reverse_by_manager = True
            elif leave.approval_date:
                diff_days = (now - leave.approval_date).total_seconds() / 86400.0
                leave.can_reverse_by_manager = diff_days <= 5.0
            else:
                leave.can_reverse_by_manager = True

    @api.onchange('presumed_delivery_date')
    def _onchange_presumed_delivery_date(self):
        if self.presumed_delivery_date and self.holiday_status_id.fixed_duration == 30:
            self.request_date_to = self.presumed_delivery_date
            self.request_date_from = self.presumed_delivery_date - timedelta(days=29)

    @api.onchange('actual_delivery_date')
    def _onchange_actual_delivery_date(self):
        if self.actual_delivery_date and self.holiday_status_id.fixed_duration == 90:
            self.request_date_from = self.actual_delivery_date
            self.request_date_to = self.actual_delivery_date + timedelta(days=89)

    @api.depends('date_from', 'date_to', 'resource_calendar_id', 'holiday_status_id.request_unit', 'holiday_status_id.count_calendar_days')
    def _compute_duration(self):
        super()._compute_duration()
        for leave in self:
            if leave.holiday_status_id.count_calendar_days:
                if leave.request_date_from and leave.request_date_to:
                    delta = (leave.request_date_to - leave.request_date_from).days + 1
                    leave.number_of_days = max(0, delta)
                elif leave.date_from and leave.date_to:
                    delta = (leave.date_to.date() - leave.date_from.date()).days + 1
                    leave.number_of_days = max(0, delta)

    def _get_applicable_allocations(self):
        """
        If the leave type specifies deduct_from_type_id (e.g. Leave of Absence deducting from Annual Leave),
        search allocations belonging to that target leave type instead.
        """
        leaves_with_deduct = self.filtered(lambda l: l.holiday_status_id.deduct_from_type_id)
        if not leaves_with_deduct:
            return super()._get_applicable_allocations()

        res = super(HrLeave, self - leaves_with_deduct)._get_applicable_allocations()
        for leave in leaves_with_deduct:
            target_type = leave.holiday_status_id.deduct_from_type_id
            allocations = self.env['hr.leave.allocation'].search([
                ('employee_id', '=', leave.employee_id.id),
                ('holiday_status_id', '=', target_type.id),
                ('state', '=', 'validate'),
                '|',
                ('date_to', '=', False),
                ('date_to', '>=', leave.date_from or fields.Date.today()),
            ], order='date_to asc, id asc')
            res[leave.id] = allocations
        return res

    @api.constrains('holiday_status_id', 'employee_id', 'number_of_days')
    def _check_ethswitch_leave_policies(self):
        for leave in self:
            leave_type = leave.holiday_status_id
            emp = leave.employee_id
            if not leave_type or not emp:
                continue

            # 1. Gender restriction
            if leave_type.gender_restriction != 'all':
                if emp.gender != leave_type.gender_restriction:
                    gender_name = dict(leave_type._fields['gender_restriction'].selection).get(leave_type.gender_restriction)
                    raise ValidationError(_(
                        "The leave type '%(type)s' is restricted to %(gender)s employees only. %(emp)s is not eligible.",
                        type=leave_type.name,
                        gender=gender_name,
                        emp=emp.name
                    ))

            # 2. Permanent employees only
            if leave_type.permanent_only and emp.employee_type != 'employee':
                raise ValidationError(_(
                    "The leave type '%(type)s' is reserved exclusively for permanent employees. %(emp)s is listed as '%(emp_type)s'.",
                    type=leave_type.name,
                    emp=emp.name,
                    emp_type=emp.employee_type or 'unspecified'
                ))

            # 3. Fixed duration check
            if leave_type.fixed_duration > 0:
                if abs(leave.number_of_days - leave_type.fixed_duration) > 0.01:
                    raise ValidationError(_(
                        "Requests for '%(type)s' must be exactly %(fixed)s days (currently %(current)s days).",
                        type=leave_type.name,
                        fixed=leave_type.fixed_duration,
                        current=leave.number_of_days
                    ))

            # 4. Maximum duration per request check
            if leave_type.max_duration_per_request > 0:
                if leave.number_of_days > leave_type.max_duration_per_request:
                    raise ValidationError(_(
                        "Requests for '%(type)s' cannot exceed %(max)s days (currently %(current)s days).",
                        type=leave_type.name,
                        max=leave_type.max_duration_per_request,
                        current=leave.number_of_days
                    ))

            # 5. Nil annual leave balance requirement for Leave Without Pay
            if leave_type.require_zero_annual_balance:
                annual_leave_types = self.env['hr.leave.type'].search([
                    ('name', 'ilike', 'Annual'),
                ])
                if annual_leave_types:
                    emp_data = annual_leave_types.get_allocation_data(emp)
                    remaining = 0.0
                    for data in emp_data.get(emp, []):
                        remaining += data[1].get('virtual_remaining_leaves', 0.0)
                    if remaining > 0.0:
                        raise ValidationError(_(
                            "Leave Without Pay can only be requested when there is no outstanding Annual Leave balance. %(emp)s currently has %(rem).2f remaining Annual Leave days.",
                            emp=emp.name,
                            rem=remaining
                        ))

    def action_validate(self, *args, **kwargs):
        res = super().action_validate(*args, **kwargs)
        for leave in self:
            if not leave.approval_date:
                leave.approval_date = fields.Datetime.now()
        return res

    def action_approve(self, *args, **kwargs):
        res = super().action_approve(*args, **kwargs)
        for leave in self:
            if not leave.approval_date:
                leave.approval_date = fields.Datetime.now()
        return res

    def action_refuse(self, *args, **kwargs):
        self._check_manager_reversal_window()
        return super().action_refuse(*args, **kwargs)

    def action_cancel(self, *args, **kwargs):
        self._check_manager_reversal_window()
        return super().action_cancel(*args, **kwargs)

    def _check_manager_reversal_window(self):
        """
        Enforces EthSwitch policy: Supervisors may only cancel or refuse approved leave
        within 5 days of the approval date. After 5 days, only HR Officers can reverse.
        """
        is_hr_user = self.env.user.has_group('hr_holidays.group_hr_holidays_user')
        if is_hr_user:
            return

        now = fields.Datetime.now()
        for leave in self:
            if leave.state in ['validate1', 'validate'] and leave.approval_date:
                diff_days = (now - leave.approval_date).total_seconds() / 86400.0
                if diff_days > 5.0:
                    raise UserError(_(
                        "Supervisors can only cancel or refuse approved leave within 5 days of the approval date (approved on %(date)s). Please contact the HR Department to perform a reversal.",
                        date=leave.approval_date.strftime('%Y-%m-%d %H:%M')
                    ))
