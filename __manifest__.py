# -*- coding: utf-8 -*-
{
    'name': 'EthSwitch Time Off Management',
    'version': '18.0.1.0.0',
    'category': 'Human Resources/Time Off',
    'summary': 'Tailored Leave Management for EthSwitch S.C. adhering to company leave policies and Ethiopian Labor standards',
    'description': """
EthSwitch S.C. Leave Management System
======================================
Custom Leave Management extension for Odoo 18 Enterprise designed specifically for EthSwitch S.C.

Key Features & Business Policies:
---------------------------------
1. **Eligibility & Continuous Calendar Counting**:
   - Distinct leave rules for permanent employees.
   - Continuous calendar-day duration counting for Sick, Prenatal, Postnatal, and Paternity leave.
   - Gender-specific leave eligibility (Prenatal/Postnatal for female staff, Paternity for male staff).
   - Fixed and maximum durations per request (e.g., 30 days Prenatal, 90 days Postnatal, 3 days Paternity/Wedding/Mourning).

2. **Annual Leave Rules & Reversals**:
   - Leave of Absence directly deducts from Annual Leave balance while remaining distinct for reporting.
   - Leave Without Pay requires zero remaining Annual Leave balance as a precondition.
   - 5-Day Undo Window: Supervisors can only cancel/refuse approved leave within 5 calendar days of approval; thereafter, only HR Officers can reverse.
   - Hospitalization / Medical Reversal Wizard: Partial or full reversal of Annual Leave to Sick Leave with attached medical certificate upon HR approval.
   - Two-Budget-Year Accumulation & Expiry: Automated monitoring and advance notice before leave forfeiture.
   - Leave Postponement workflow allowing special extension of accumulated leave.

3. **Annual Leave Scheduling**:
   - Fiscal-year leave planning for employees with immediate supervisor review and HR validation.
   - Prohibits scheduling outside the fiscal year or on negative projected balance.
   - Automatic generation of approved leave bookings upon schedule confirmation.
   - Adherence and plan-versus-actual tracking.

4. **Monetary Valuation in Birr (ETB) & Final Settlement**:
   - Automated conversion of remaining leave days into monetary value based on basic contract wage and configurable daily divisor.
   - Formal Leave Settlement Statement report for active and terminated employees.
    """,
    'author': 'EthSwitch S.C. / Antigravity',
    'website': 'https://www.ethswitch.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'base_setup',
        'mail',
        'hr',
        'hr_holidays',
        'hr_contract',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/ir_cron_data.xml',
        'data/mail_template_data.xml',
        'data/leave_type_data.xml',
        'wizard/hr_leave_reversal_wizard_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_leave_type_views.xml',
        'views/hr_leave_views.xml',
        'views/hr_leave_postponement_views.xml',
        'views/hr_leave_schedule_views.xml',
        'views/hr_employee_views.xml',
        'views/menu_views.xml',
        'report/leave_settlement_templates.xml',
        'report/leave_settlement_report.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
