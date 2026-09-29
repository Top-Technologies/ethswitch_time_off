# -*- coding: utf-8 -*-
from datetime import datetime, date
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class HrLeaveSchedule(models.Model):
    _name = 'hr.leave.schedule'
    _description = 'Annual Leave Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fiscal_year desc, employee_id asc, id desc'

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
        default=lambda self: self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')], limit=1)
    )

    fiscal_year = fields.Char(
        string='Fiscal Year',
        required=True,
        default=lambda self: self._default_fiscal_year(),
        help="The coming fiscal/budget year for advance scheduling (e.g. 2017 EFY or 2024/2025)."
    )

    fiscal_year_start = fields.Date(
        string='Fiscal Year Start Date',
        required=True,
        default=lambda self: self._default_fiscal_year_dates()[0]
    )

    fiscal_year_end = fields.Date(
        string='Fiscal Year End Date',
        required=True,
        default=lambda self: self._default_fiscal_year_dates()[1]
    )

    line_ids = fields.One2many(
        'hr.leave.schedule.line',
        'schedule_id',
        string='Schedule Lines',
        copy=True
    )

    total_planned_days = fields.Float(
        string='Total Planned Days',
        compute='_compute_total_planned_days',
        store=True,
        tracking=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'To Approve'),
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

    @api.model
    def _default_fiscal_year(self):
        today = fields.Date.today()
        # Ethiopian fiscal year starts in July (month 7)
        if today.month >= 7:
            return f"{today.year}/{today.year + 1}"
        return f"{today.year - 1}/{today.year}"

    @api.model
    def _default_fiscal_year_dates(self):
        company = self.env.company
        month = int(company.fiscal_year_start_month or 7)
        day = company.fiscal_year_start_day or 8
        today = fields.Date.today()
        year = today.year if today.month >= month else today.year - 1
        start_date = date(year, month, day)
        end_date = date(year + 1, month, day) - fields.Date.to_date('0001-01-02') + fields.Date.to_date('0001-01-01')
        return start_date, end_date

    @api.depends('line_ids.number_of_days')
    def _compute_total_planned_days(self):
        for rec in self:
            rec.total_planned_days = sum(rec.line_ids.mapped('number_of_days'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.leave.schedule') or _('ALS')
        return super().create(vals_list)

    @api.constrains('fiscal_year_start', 'fiscal_year_end')
    def _check_fiscal_dates(self):
        for rec in self:
            if rec.fiscal_year_end <= rec.fiscal_year_start:
                raise ValidationError(_("Fiscal Year End Date must be after Fiscal Year Start Date."))

    def action_submit(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Please add at least one schedule line before submitting."))
        self.write({'state': 'confirm'})
        # Notify immediate supervisor
        if self.manager_id and self.manager_id.user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Annual Leave Schedule for %s needs your approval') % self.employee_id.name,
                user_id=self.manager_id.user_id.id
            )

    def action_approve(self):
        self.ensure_one()
        current_user = self.env.user
        is_manager = current_user.employee_id == self.manager_id or current_user.has_group('hr_holidays.group_hr_holidays_user')
        if not is_manager:
            raise UserError(_("Only the employee's immediate supervisor or an HR Officer can approve this leave schedule."))

        # Create future-dated approved leave requests for each line
        for line in self.line_ids.filtered(lambda l: l.state == 'draft'):
            leave_vals = {
                'name': _("Scheduled Leave (%s)") % self.fiscal_year,
                'holiday_status_id': self.leave_type_id.id,
                'employee_id': self.employee_id.id,
                'request_date_from': line.date_from,
                'request_date_to': line.date_to,
                'date_from': datetime.combine(line.date_from, datetime.min.time()),
                'date_to': datetime.combine(line.date_to, datetime.max.time()),
                'number_of_days': line.number_of_days,
                'schedule_line_id': line.id,
            }
            leave = self.env['hr.leave'].create(leave_vals)
            leave.action_validate()
            line.write({
                'leave_id': leave.id,
                'state': 'approved'
            })

        self.write({
            'state': 'validate',
            'approved_by_id': current_user.id,
            'approval_date': fields.Datetime.now(),
        })

        # Send notification email to employee
        template = self.env.ref('ethswitch_time_off.mail_template_schedule_approved', raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)
        else:
            self.message_post(body=_(
                "Annual Leave Schedule approved. Employee has been notified to adhere to the approved schedule."
            ))

    def action_refuse(self):
        self.ensure_one()
        self.write({'state': 'refuse'})
        self.line_ids.write({'state': 'cancelled'})
        self.message_post(body=_("Annual Leave Schedule has been refused."))

    def action_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})
        self.line_ids.write({'state': 'draft'})


class HrLeaveScheduleLine(models.Model):
    _name = 'hr.leave.schedule.line'
    _description = 'Annual Leave Schedule Line'
    _order = 'date_from asc, id asc'

    schedule_id = fields.Many2one(
        'hr.leave.schedule',
        string='Schedule',
        required=True,
        ondelete='cascade'
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='schedule_id.employee_id',
        store=True,
        readonly=True
    )

    date_from = fields.Date(
        string='Start Date',
        required=True
    )

    date_to = fields.Date(
        string='End Date',
        required=True
    )

    number_of_days = fields.Float(
        string='Planned Days',
        compute='_compute_number_of_days',
        store=True,
        readonly=False,
        required=True
    )

    fiscal_quarter = fields.Selection([
        ('q1', 'Quarter 1 (Jul - Sep)'),
        ('q2', 'Quarter 2 (Oct - Dec)'),
        ('q3', 'Quarter 3 (Jan - Mar)'),
        ('q4', 'Quarter 4 (Apr - Jun)'),
    ], string='Fiscal Quarter', compute='_compute_fiscal_quarter', store=True)

    leave_id = fields.Many2one(
        'hr.leave',
        string='Generated Time Off',
        readonly=True,
        copy=False
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('approved', 'Approved'),
        ('taken', 'Taken'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', readonly=True)

    notes = fields.Char(string='Notes / Purpose')

    @api.depends('date_from', 'date_to', 'schedule_id.employee_id')
    def _compute_number_of_days(self):
        for line in self:
            if line.date_from and line.date_to:
                if line.date_to < line.date_from:
                    line.number_of_days = 0.0
                    continue
                # Calculate working days based on employee resource calendar
                calendar = line.schedule_id.employee_id.resource_calendar_id or self.env.company.resource_calendar_id
                if calendar:
                    dt_from = datetime.combine(line.date_from, datetime.min.time())
                    dt_to = datetime.combine(line.date_to, datetime.max.time())
                    days_data = calendar.get_work_duration_data(dt_from, dt_to, compute_leaves=True)
                    line.number_of_days = days_data.get('days', 0.0)
                else:
                    line.number_of_days = (line.date_to - line.date_from).days + 1
            else:
                line.number_of_days = 0.0

    @api.depends('date_from')
    def _compute_fiscal_quarter(self):
        for line in self:
            if line.date_from:
                month = line.date_from.month
                if month in [7, 8, 9]:
                    line.fiscal_quarter = 'q1'
                elif month in [10, 11, 12]:
                    line.fiscal_quarter = 'q2'
                elif month in [1, 2, 3]:
                    line.fiscal_quarter = 'q3'
                else:
                    line.fiscal_quarter = 'q4'
            else:
                line.fiscal_quarter = False

    @api.constrains('date_from', 'date_to', 'schedule_id')
    def _check_schedule_line_dates(self):
        for line in self:
            if line.date_to < line.date_from:
                raise ValidationError(_("End Date cannot be earlier than Start Date."))

            sched = line.schedule_id
            if sched.fiscal_year_start and sched.fiscal_year_end:
                if line.date_from < sched.fiscal_year_start or line.date_to > sched.fiscal_year_end:
                    raise ValidationError(_(
                        "Schedule line dates (%(start)s to %(end)s) must fall strictly within the fiscal year period (%(fy_start)s to %(fy_end)s).",
                        start=line.date_from,
                        end=line.date_to,
                        fy_start=sched.fiscal_year_start,
                        fy_end=sched.fiscal_year_end
                    ))

    def action_cancel_line(self):
        """Allows supervisor or HR to cancel/reverse an individual schedule line within policy window."""
        self.ensure_one()
        current_user = self.env.user
        is_manager = current_user.employee_id == self.schedule_id.manager_id or current_user.has_group('hr_holidays.group_hr_holidays_user')
        if not is_manager:
            raise UserError(_("Only the immediate supervisor or HR can cancel a scheduled leave line."))

        if self.leave_id and self.leave_id.state in ['confirm', 'validate']:
            self.leave_id.action_refuse()

        self.write({'state': 'cancelled'})
        self.schedule_id.message_post(body=_(
            "Schedule line from %(dfrom)s to %(dto)s was cancelled by %(user)s.",
            dfrom=self.date_from, dto=self.date_to, user=current_user.name
        ))
