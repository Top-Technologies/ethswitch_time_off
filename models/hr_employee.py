# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields, models, api, _


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )

    accrued_annual_leaves = fields.Float(
        string='Accrued Annual Leave (Days)',
        compute='_compute_annual_leave_balances',
        help="Total annual leave days accrued to date."
    )

    utilized_annual_leaves = fields.Float(
        string='Utilized Annual Leave (Days)',
        compute='_compute_annual_leave_balances',
        help="Total annual leave days utilized/taken to date."
    )

    remaining_annual_leaves = fields.Float(
        string='Remaining Annual Leave (Days)',
        compute='_compute_annual_leave_balances',
        help="Current remaining annual leave balance in days."
    )

    daily_wage_rate = fields.Monetary(
        string='Daily Wage Rate (Birr)',
        currency_field='currency_id',
        compute='_compute_annual_leave_balances',
        help="Daily wage rate computed as Basic Contract Salary divided by Leave Encashment Divisor."
    )

    annual_leave_monetary_value = fields.Monetary(
        string='Leave Balance Value (Birr)',
        currency_field='currency_id',
        compute='_compute_annual_leave_balances',
        help="Monetary liability / payable value of remaining annual leave in Ethiopian Birr."
    )

    def _compute_annual_leave_balances(self):
        annual_types = self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')])
        for emp in self:
            accrued = 0.0
            utilized = 0.0
            remaining = 0.0

            if annual_types:
                # Retrieve allocation data for annual leave types
                alloc_data = annual_types.get_allocation_data(emp)
                for item in alloc_data.get(emp, []):
                    accrued += item[1].get('max_leaves', 0.0)
                    utilized += item[1].get('leaves_taken', 0.0)
                    remaining += item[1].get('virtual_remaining_leaves', 0.0)

            emp.accrued_annual_leaves = accrued
            emp.utilized_annual_leaves = utilized
            emp.remaining_annual_leaves = remaining

            # Compute monetary valuation
            divisor = emp.company_id.leave_encashment_divisor or 26.0
            contract = emp.contract_id or self.env['hr.contract'].search([
                ('employee_id', '=', emp.id),
                ('state', 'in', ['open', 'close']),
            ], order='date_start desc', limit=1)

            basic_wage = contract.wage if contract else 0.0
            daily_rate = basic_wage / divisor if divisor > 0 else 0.0

            emp.daily_wage_rate = daily_rate
            emp.annual_leave_monetary_value = max(0.0, remaining * daily_rate)

    @api.model
    def _cron_check_annual_leave_expiry(self):
        """
        Scheduled action checking accumulated annual leave across two budget years.
        Notifies staff and their immediate supervisor about expiring leave.
        """
        today = fields.Date.today()
        annual_types = self.env['hr.leave.type'].search([('name', 'ilike', 'Annual')])
        if not annual_types:
            return

        template = self.env.ref('ethswitch_time_off.mail_template_leave_expiry_warning', raise_if_not_found=False)
        employees = self.search([('active', '=', True)])

        for emp in employees:
            warning_days = emp.company_id.leave_expiry_warning_days or 30
            allocations = self.env['hr.leave.allocation'].search([
                ('employee_id', '=', emp.id),
                ('holiday_status_id', 'in', annual_types.ids),
                ('state', '=', 'validate'),
                ('date_to', '!=', False),
                ('date_to', '>=', today),
                ('date_to', '<=', today + timedelta(days=warning_days)),
            ])
            for alloc in allocations:
                has_postponement = self.env['hr.leave.postponement'].search_count([
                    ('employee_id', '=', emp.id),
                    ('state', '=', 'validate'),
                    ('original_expiry_date', '=', alloc.date_to),
                ])
                if not has_postponement and template:
                    template.with_context(
                        expiring_days=alloc.number_of_days_display,
                        expiry_date=alloc.date_to
                    ).send_mail(emp.id, force_send=True)

