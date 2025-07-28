# -*- coding: utf-8 -*-

from odoo import models, fields, tools, api
from datetime import datetime, timedelta

class ContractorStatementAnalysisReport(models.Model):
    _name = 'contractor.statement.analysis.report'
    _description = 'Contractor Statement Analysis Report'
    _auto = False
    _order = 'statement_date desc'
    _rec_name = 'name'

    # Basic Fields
    name = fields.Char(string='Statement Number', readonly=True)
    project_id = fields.Many2one('project.config', string='Project', readonly=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', readonly=True)
    contractor_id = fields.Many2one('res.partner', string='Contractor', readonly=True)
    contractor_type = fields.Selection([
        ('main', 'Main Contractor'),
        ('sub', 'Sub Contractor')
    ], string='Contractor Type', readonly=True)
    statement_date = fields.Date(string='Statement Date', readonly=True)
    product_id = fields.Many2one('contractor.product', string='Product', readonly=True)
    
    # Quantity Fields
    contract_qty = fields.Float(string='Contract Quantity', readonly=True)
    current_qty = fields.Float(string='Current Quantity', readonly=True)
    total_qty = fields.Float(string='Total Quantity', readonly=True)
    prev_qty = fields.Float(string='Previous Quantity', readonly=True)
    remaining_qty = fields.Float(string='Remaining Quantity', readonly=True)
    
    # Progress Fields
    progress_percent = fields.Float(string='Progress %', readonly=True)
    progress_range = fields.Selection([
        ('0-25', '0-25%'),
        ('26-50', '26-50%'),
        ('51-75', '51-75%'),
        ('76-100', '76-100%'),
        ('completed', 'Completed')
    ], string='Progress Range', readonly=True)
    
    # Financial Fields
    unit_price = fields.Float(string='Unit Price', readonly=True)
    current_value = fields.Float(string='Current Value', readonly=True)
    total_value = fields.Float(string='Total Value', readonly=True)
    gross_value = fields.Float(string='Gross Value', readonly=True)
    tax_amount = fields.Float(string='Tax Amount', readonly=True)
    
    # Deductions
    advance_payment_deduction = fields.Float(string='Advance Payment Deduction', readonly=True)
    retention_percentage = fields.Float(string='Retention %', readonly=True)
    retention = fields.Float(string='Retention Amount', readonly=True)
    other_deductions = fields.Float(string='Other Deductions', readonly=True)
    total_deductions = fields.Float(string='Total Deductions', readonly=True)
    
    # Net Amount
    net_payable = fields.Float(string='Net Payable', readonly=True)
    
    # Value Range Classification
    value_range = fields.Selection([
        ('small', 'Small (<50k)'),
        ('medium', 'Medium (50k-200k)'),
        ('large', 'Large (200k-500k)'),
        ('xlarge', 'Extra Large (>500k)')
    ], string='Value Range', readonly=True)
    
    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled')
    ], string='Status', readonly=True)
    
    # Date Analysis
    month = fields.Char(string='Month', readonly=True)
    year = fields.Char(string='Year', readonly=True)
    quarter = fields.Char(string='Quarter', readonly=True)
    week = fields.Char(string='Week', readonly=True)
    
    # Payment Analysis
    payment_delay_days = fields.Integer(string='Payment Delay Days', readonly=True)
    payment_status = fields.Selection([
        ('on_time', 'On Time'),
        ('delayed', 'Delayed'),
        ('overdue', 'Overdue')
    ], string='Payment Status', readonly=True)
    
    # Performance Metrics
    efficiency_ratio = fields.Float(string='Efficiency Ratio', readonly=True)
    cost_per_unit = fields.Float(string='Cost per Unit', readonly=True)
    variance_percentage = fields.Float(string='Variance %', readonly=True)
    
    # Currency
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    
    # Work Period
    work_period_from = fields.Date(string='Work Period From', readonly=True)
    work_period_to = fields.Date(string='Work Period To', readonly=True)
    work_duration_days = fields.Integer(string='Work Duration (Days)', readonly=True)
    
    # Contractor Performance
    contractor_rating = fields.Float(string='Contractor Rating', readonly=True)
    quality_score = fields.Float(string='Quality Score', readonly=True)
    delivery_score = fields.Float(string='Delivery Score', readonly=True)
    
    # Project Information
    project_location = fields.Char(string='Project Location', readonly=True)
    project_manager = fields.Many2one('res.users', string='Project Manager', readonly=True)
    project_start_date = fields.Date(string='Project Start Date', readonly=True)
    project_end_date = fields.Date(string='Project End Date', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    s.name,
                    s.project_id,
                    s.work_type_id,
                    s.contractor_id,
                    s.contractor_type,
                    s.statement_date,
                    s.work_period_from,
                    s.work_period_to,
                    CASE 
                        WHEN s.work_period_to IS NOT NULL AND s.work_period_from IS NOT NULL 
                        THEN s.work_period_to - s.work_period_from
                        ELSE 0
                    END AS work_duration_days,
                    l.product_id,
                    l.unit_price,
                    l.contract_qty,
                    l.current_qty,
                    l.total_qty,
                    l.prev_qty,
                    CASE 
                        WHEN l.contract_qty > 0 
                        THEN l.contract_qty - l.total_qty
                        ELSE 0
                    END AS remaining_qty,
                    l.progress_percent,
                    CASE 
                        WHEN l.progress_percent < 26 THEN '0-25'
                        WHEN l.progress_percent < 51 THEN '26-50'
                        WHEN l.progress_percent < 76 THEN '51-75'
                        WHEN l.progress_percent < 100 THEN '76-100'
                        ELSE 'completed'
                    END AS progress_range,
                    l.current_value,
                    l.total_value,
                    s.gross_value,
                    s.tax_amount,
                    s.advance_payment_deduction,
                    s.retention_percentage,
                    s.retention,
                    s.other_deductions,
                    s.total_deductions,
                    s.net_payable,
                    CASE 
                        WHEN s.net_payable < 50000 THEN 'small'
                        WHEN s.net_payable < 200000 THEN 'medium'
                        WHEN s.net_payable < 500000 THEN 'large'
                        ELSE 'xlarge'
                    END AS value_range,
                    s.state,
                    to_char(s.statement_date, 'Month YYYY') AS month,
                    to_char(s.statement_date, 'YYYY') AS year,
                    'Q' || to_char(s.statement_date, 'Q') || ' ' || to_char(s.statement_date, 'YYYY') AS quarter,
                    to_char(s.statement_date, 'YYYY-"W"IW') AS week,
                    'on_time' AS payment_status,
                    0 AS payment_delay_days,
                    CASE 
                        WHEN l.contract_qty > 0 
                        THEN l.total_qty / l.contract_qty
                        ELSE 0
                    END AS efficiency_ratio,
                    CASE 
                        WHEN l.total_qty > 0 
                        THEN l.total_value / l.total_qty
                        ELSE 0
                    END AS cost_per_unit,
                    CASE 
                        WHEN l.contract_qty > 0 
                        THEN ((l.total_qty - l.contract_qty) / l.contract_qty) * 100
                        ELSE 0
                    END AS variance_percentage,
                    (SELECT id FROM res_currency WHERE name = 'EGP' LIMIT 1) AS currency_id,
                    NULL AS project_location,
                    NULL AS project_manager,
                    NULL AS project_start_date,
                    NULL AS project_end_date,
                    0 AS contractor_rating,
                    0 AS quality_score,
                    0 AS delivery_score
                FROM
                    contractor_statement s
                JOIN
                    contractor_statement_line l ON l.statement_id = s.id
                LEFT JOIN
                    project_config p ON p.id = s.project_id
                LEFT JOIN
                    res_partner c ON c.id = s.contractor_id
                WHERE
                    s.state != 'cancelled'
            )
        """ % self._table)
    
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        """Override read_group to add custom aggregations"""
        result = super(ContractorStatementAnalysisReport, self).read_group(
            domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy
        )
        
        # Add custom calculations for grouped data
        for group in result:
            if group.get('__count', 0) > 0:
                # Calculate average efficiency for the group
                if 'efficiency_ratio' in fields:
                    group['efficiency_ratio'] = group.get('efficiency_ratio', 0)
                
                # Calculate payment performance
                if 'payment_delay_days' in fields and group.get('payment_delay_days'):
                    if group['payment_delay_days'] <= 0:
                        group['payment_performance'] = 'excellent'
                    elif group['payment_delay_days'] <= 15:
                        group['payment_performance'] = 'good'
                    elif group['payment_delay_days'] <= 30:
                        group['payment_performance'] = 'average'
                    else:
                        group['payment_performance'] = 'poor'
        
        return result
    
    def action_view_statements(self):
        """Action to view related statements"""
        statements = self.env['contractor.statement'].search([
            ('project_id', '=', self.project_id.id),
            ('contractor_id', '=', self.contractor_id.id),
            ('work_type_id', '=', self.work_type_id.id)
        ])
        
        return {
            'name': 'Related Statements',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'contractor.statement',
            'domain': [('id', 'in', statements.ids)],
            'context': {'default_project_id': self.project_id.id}
        }
    
    def action_view_contractor_profile(self):
        """Action to view contractor profile"""
        return {
            'name': 'Contractor Profile',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'res.partner',
            'res_id': self.contractor_id.id,
            'context': {'default_is_contractor': True}
        }
    
    def action_view_project_details(self):
        """Action to view project details"""
        return {
            'name': 'Project Details',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'project.config',
            'res_id': self.project_id.id,
        }