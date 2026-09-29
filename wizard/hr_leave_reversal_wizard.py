# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError


class HrLeaveReversalWizard(models.TransientModel):
    _name = 'hr.leave.reversal.wizard'
    _description = 'Annual Leave Reversal (Medical / Hospitalization)'

    leave_id = fields.Many2one(
        'hr.leave',
        string='Annual Leave Request',
        required=True,
        default=lambda self: self.env.context.get('active_id')
    )

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='leave_id.employee_id',
        readonly=True
    )

    leave_date_from = fields.Date(
        string='Original Start Date',
        related='leave_id.request_date_from',
        readonly=True
    )

    leave_date_to = fields.Date(
        string='Original End Date',
        related='leave_id.request_date_to',
        readonly=True
    )

    reversal_date_from = fields.Date(
        string='Hospitalization Start Date',
        required=True
    )

    reversal_date_to = fields.Date(
        string='Hospitalization End Date',
        required=True
    )

    days_to_reverse = fields.Float(
        string='Days to Convert to Sick Leave',
        compute='_compute_days_to_reverse',
        store=True,
        readonly=False,
        required=True
    )

    reason = fields.Text(
        string='Medical Reason / Diagnosis',
        required=True,
        default=lambda self: _("Hospitalized / medically treated during annual leave.")
    )

    medical_certificate = fields.Binary(
        string='Medical Certificate / Proof',
        required=True,
        attachment=True,
        help="Upload supporting medical certificate or hospital admission document."
    )

    certificate_filename = fields.Char(string='Certificate Filename')

    @api.depends('reversal_date_from', 'reversal_date_to', 'leave_id')
    def _compute_days_to_reverse(self):
        for wiz in self:
            if wiz.reversal_date_from and wiz.reversal_date_to and wiz.leave_id:
                if wiz.reversal_date_to < wiz.reversal_date_from:
                    wiz.days_to_reverse = 0.0
                    continue
                # Working days within the reversal period
                calendar = wiz.leave_id.employee_id.resource_calendar_id or self.env.company.resource_calendar_id
                if calendar:
                    dt_from = datetime.combine(wiz.reversal_date_from, datetime.min.time())
                    dt_to = datetime.combine(wiz.reversal_date_to, datetime.max.time())
                    duration = calendar.get_work_duration_data(dt_from, dt_to, compute_leaves=False)
                    wiz.days_to_reverse = duration.get('days', 0.0)
                else:
                    wiz.days_to_reverse = (wiz.reversal_date_to - wiz.reversal_date_from).days + 1
            else:
                wiz.days_to_reverse = 0.0

    @api.constrains('reversal_date_from', 'reversal_date_to', 'leave_id')
    def _check_reversal_dates(self):
        for wiz in self:
            if wiz.reversal_date_to < wiz.reversal_date_from:
                raise ValidationError(_("Hospitalization End Date cannot be before Start Date."))
            if wiz.leave_id:
                orig_start = wiz.leave_id.request_date_from or (wiz.leave_id.date_from and wiz.leave_id.date_from.date())
                orig_end = wiz.leave_id.request_date_to or (wiz.leave_id.date_to and wiz.leave_id.date_to.date())
                if orig_start and orig_end:
                    if wiz.reversal_date_from < orig_start or wiz.reversal_date_to > orig_end:
                        raise ValidationError(_(
                            "Hospitalization dates (%(r_start)s to %(r_end)s) must fall within the original annual leave period (%(l_start)s to %(l_end)s).",
                            r_start=wiz.reversal_date_from,
                            r_end=wiz.reversal_date_to,
                            l_start=orig_start,
                            l_end=orig_end
                        ))

    def action_confirm_reversal(self):
        self.ensure_one()
        if not self.env.user.has_group('hr_holidays.group_hr_holidays_user'):
            raise UserError(_("Only HR Department Officers can approve Annual Leave Reversals."))

        leave = self.leave_id
        if leave.state != 'validate':
            raise UserError(_("Only approved annual leave can be reversed."))

        orig_start = leave.request_date_from or (leave.date_from.date() if isinstance(leave.date_from, datetime) else leave.date_from)
        orig_end = leave.request_date_to or (leave.date_to.date() if isinstance(leave.date_to, datetime) else leave.date_to)
        rev_start = self.reversal_date_from
        rev_end = self.reversal_date_to

        # 1. Find or verify Sick Leave type
        sick_leave_type = self.env['hr.leave.type'].search([('name', 'ilike', 'Sick')], limit=1)
        if not sick_leave_type:
            raise UserError(_("Sick Leave type was not found. Please configure a Sick Leave type first."))

        context_skip = {
            'leave_skip_state_check': True,
            'leave_skip_date_check': True,
            'mail_create_nosubscribe': True,
        }

        # 2. Remove existing resource leaves for the original leave
        leave._remove_resource_leave()

        # 3. Adjust or cancel the original annual leave to free up the reversed dates
        if rev_start == orig_start and rev_end == orig_end:
            # Full reversal
            leave.with_context(**context_skip).action_refuse()
        elif rev_start == orig_start and rev_end < orig_end:
            # Reversal at the start: shorten original leave
            new_start = rev_end + timedelta(days=1)
            leave.with_context(**context_skip).write({
                'request_date_from': new_start,
                'date_from': datetime.combine(new_start, datetime.min.time()),
            })
            leave._create_resource_leave()
        elif rev_start > orig_start and rev_end == orig_end:
            # Reversal at the end: shorten original leave
            new_end = rev_start - timedelta(days=1)
            leave.with_context(**context_skip).write({
                'request_date_to': new_end,
                'date_to': datetime.combine(new_end, datetime.max.time()),
            })
            leave._create_resource_leave()
        else:
            # Reversal in the middle: shorten original and create tail leave
            new_end = rev_start - timedelta(days=1)
            leave.with_context(**context_skip).write({
                'request_date_to': new_end,
                'date_to': datetime.combine(new_end, datetime.max.time()),
            })
            leave._create_resource_leave()

            tail_start = rev_end + timedelta(days=1)
            tail_vals = {
                'name': leave.name or _("Annual Leave"),
                'holiday_status_id': leave.holiday_status_id.id,
                'employee_id': leave.employee_id.id,
                'request_date_from': tail_start,
                'request_date_to': orig_end,
                'date_from': datetime.combine(tail_start, datetime.min.time()),
                'date_to': datetime.combine(orig_end, datetime.max.time()),
            }
            tail_leave = self.env['hr.leave'].with_context(**context_skip).create(tail_vals)
            tail_leave.with_context(**context_skip).action_validate()

        # 4. Create the approved Sick Leave record for the reversed period
        sick_leave_vals = {
            'name': _("Medical Reversal from Annual Leave (%s)") % (leave.name or _("Annual Leave")),
            'holiday_status_id': sick_leave_type.id,
            'employee_id': leave.employee_id.id,
            'request_date_from': rev_start,
            'request_date_to': rev_end,
            'date_from': datetime.combine(rev_start, datetime.min.time()),
            'date_to': datetime.combine(rev_end, datetime.max.time()),
            'number_of_days': self.days_to_reverse,
            'notes': _("Reversed from Annual Leave %(leave)s due to hospitalization/illness. Reason: %(reason)s",
                       leave=leave.display_name, reason=self.reason),
        }
        sick_leave = self.env['hr.leave'].with_context(**context_skip).create(sick_leave_vals)
        sick_leave.with_context(**context_skip).action_validate()

        # 5. Attach medical certificate if provided
        if self.medical_certificate:
            attachment_vals = {
                'name': self.certificate_filename or _('Medical_Certificate.pdf'),
                'datas': self.medical_certificate,
                'res_model': 'hr.leave',
                'res_id': sick_leave.id,
            }
            self.env['ir.attachment'].create(attachment_vals)

        # 6. Log in Chatter
        leave.message_post(body=_(
            "<b>Annual Leave Reversal Approved by HR:</b><br/>"
            "- Hospitalized Period: %(dfrom)s to %(dto)s (%(days).2f days)<br/>"
            "- Converted to Sick Leave: %(sick_link)s<br/>"
            "- Reason: %(reason)s",
            dfrom=rev_start,
            dto=rev_end,
            days=self.days_to_reverse,
            sick_link=sick_leave.display_name,
            reason=self.reason
        ))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Leave Reversed Successfully'),
                'message': _('%(days).2f days have been converted to Sick Leave and restored to Annual Leave balance.',
                             days=self.days_to_reverse),
                'type': 'success',
                'sticky': False,
            }
        }
