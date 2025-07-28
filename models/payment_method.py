# -*- coding: utf-8 -*-

from odoo import models, fields, api

class PaymentMethodConfig(models.Model):
    _name = 'payment.method.config'
    _description = 'Payment Method Configuration'
    
    name = fields.Char(string='Payment Method Name', required=True)
    code = fields.Char(string='Code', required=True)
    journal_id = fields.Many2one('account.journal', string='Payment Journal', required=True, domain=[('type', 'in', ['bank', 'cash'])])
    payment_type = fields.Selection([
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
        ('both', 'Both')
    ], string='Payment Type', required=True, default='both')
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Payment method code must be unique!')
    ]
