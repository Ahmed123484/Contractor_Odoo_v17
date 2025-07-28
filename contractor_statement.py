# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ContractorStatement(models.Model):
    _name = 'contractor.statement'
    _description = 'Contractor Statement'
    _order = 'statement_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Statement Number', required=True, copy=False, readonly=True, default='New')
    project_id = fields.Many2one('project.config', string='Project Name', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    contractor_id = fields.Many2one('res.partner', string='Contractor Name', required=True, domain=[('is_company', '=', True)])
    contractor_type = fields.Selection([
        ('main', 'Main Contractor'),
        ('sub', 'Sub Contractor')
    ], string='Contractor Type', required=True, default='main')
    statement_date = fields.Date(string='Statement Date', required=True, default=fields.Date.today)
    work_period_from = fields.Date(string='Work Period From', required=True)
    work_period_to = fields.Date(string='Work Period To', required=True)
    
    
    # Statement Lines
    statement_line_ids = fields.One2many('contractor.statement.line', 'statement_id', string='Statement Lines')
    
    # Financial Fields
    gross_value = fields.Float(string='Gross Value', compute='_compute_amounts', store=True)
    advance_payment_deduction = fields.Float(string='Advance Payment Deduction', default=0.0)
    retention_percentage = fields.Float(string='Retention %', default=5.0)
    retention = fields.Float(string='Retention', default=0.0)  # Not computed, editable
    tax_ids = fields.Many2many('account.tax', string='Taxes')
    tax_amount = fields.Float(string='Tax Amount', compute='_compute_amounts', store=True)
    other_deductions = fields.Float(string='Other Deductions', default=0.0)
    advance_payment_account_id = fields.Many2one('account.account', string='Advance Payment Account', readonly=True)
    retention_account_id = fields.Many2one('account.account', string='Retention Account', readonly=True)
    other_deductions_account_id = fields.Many2one('account.account', string='Other Deductions Account', readonly=True)
    # NEW: Separate fields for totals
    subtotal = fields.Float(string='Subtotal (Gross + Taxes)', compute='_compute_amounts', store=True)
    total_deductions = fields.Float(string='Total Deductions', compute='_compute_amounts', store=True)
    net_payable = fields.Float(string='Net Payable', compute='_compute_amounts', store=True)
    
    # Signatures
    contractor_signature = fields.Char(string='Contractor/Preparer Signature')
    consultant_signature = fields.Char(string='Consultant Signature')
    project_owner_signature = fields.Char(string='Project Owner Signature')
    
    # Accounting
    journal_id = fields.Many2one('account.journal', string='Journal', domain=[('type', '=', 'general')])
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    payment_id = fields.Many2one('account.payment', string='Payment', readonly=True)
    payment_method_id = fields.Many2one('payment.method.config', string='Payment Method')
    payment_notes = fields.Text(string='Payment Notes')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
        ('paid', 'Paid'),
    ], string='Status', default='draft', tracking=True)
    
    # User tracking fields
    created_by = fields.Many2one('res.users', string='Created By', default=lambda self: self.env.user, readonly=True)
    created_date = fields.Datetime(string='Created Date', default=fields.Datetime.now, readonly=True)
    confirmed_by = fields.Many2one('res.users', string='Confirmed By', readonly=True)
    confirmed_date = fields.Datetime(string='Confirmed Date', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Datetime(string='Approved Date', readonly=True)
    paid_by = fields.Many2one('res.users', string='Paid By', readonly=True)
    paid_date = fields.Datetime(string='Paid Date', readonly=True)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            project_id = vals.get('project_id')
            work_type_id = vals.get('work_type_id')
            
            if project_id and work_type_id:
                project = self.env['project.config'].browse(project_id)
                work_type = self.env['work.type.config'].browse(work_type_id)
                
                # البحث عن آخر مستخلص بنفس المشروع ونوع العمل
                existing_statements = self.search([
                    ('project_id', '=', project_id),
                    ('work_type_id', '=', work_type_id)
                ], order='name desc', limit=1)
                
                if existing_statements:
                    # استخراج الرقم من آخر مستخلص وزيادته
                    last_name = existing_statements[0].name
                    parts = last_name.split('-')
                    if len(parts) >= 3:
                        try:
                            last_number = int(parts[-1])
                            next_number = last_number + 1
                        except ValueError:
                            next_number = 1
                    else:
                        next_number = 1
                else:
                    next_number = 1
                
                vals['name'] = f"{project.code}-{work_type.code}-{next_number:03d}"
        
        return super(ContractorStatement, self).create(vals)
    @api.onchange('project_id', 'work_type_id')
    def _onchange_project_work_type_deductions(self):
        """Update deduction accounts and retention percentage when project or work type changes"""
        if self.project_id or self.work_type_id:
            try:
                deduction_config = self.env['deductions.config']
                accounts = deduction_config.get_deduction_accounts(
                    project_id=self.project_id.id if self.project_id else None,
                    work_type_id=self.work_type_id.id if self.work_type_id else None
                )
                
                self.advance_payment_account_id = accounts.get('advance_payment_account_id')
                self.retention_account_id = accounts.get('retention_account_id')
                self.other_deductions_account_id = accounts.get('other_deductions_account_id')
                self.retention_percentage = accounts.get('retention_percentage', 5.0)
                # Auto-calculate retention based on percentage
                if self.gross_value and self.retention_percentage:
                    self.retention = self.gross_value * (self.retention_percentage / 100)
            except ValidationError:
                # If no configuration found, clear the accounts
                self.advance_payment_account_id = False
                self.retention_account_id = False
                self.other_deductions_account_id = False

    # FIXED: Updated calculation logic
    @api.depends('statement_line_ids.current_value', 'tax_ids', 'advance_payment_deduction', 'other_deductions', 'retention')
    def _compute_amounts(self):
        for record in self:
            # 1. حساب القيمة الإجمالية
            record.gross_value = sum(line.current_value for line in record.statement_line_ids)
            
            # 2. حساب الضرائب
            tax_amount = 0.0
            if record.tax_ids:
                for tax in record.tax_ids:
                    if tax.amount_type == 'percent':
                        tax_amount += (record.gross_value * tax.amount) / 100
                    else:
                        tax_amount += tax.amount
            record.tax_amount = tax_amount
            
            # 3. حساب المجموع الفرعي (القيمة الإجمالية + الضرائب)
            record.subtotal = record.gross_value + record.tax_amount
            
            # 4. حساب إجمالي الخصومات
            record.total_deductions = (record.advance_payment_deduction + 
                                        record.retention + record.other_deductions)
            
            # 5. حساب صافي المستحق (الصيغة الصحيحة)
            record.net_payable = record.subtotal - record.total_deductions

    @api.onchange('project_id', 'work_type_id')
    def _onchange_project_work_type(self):
        if self.project_id and self.work_type_id:
            # تحديث نسبة الاستبقاء من الإعدادات
            retention_config = self.env['retention.config'].search([
                ('project_id', '=', self.project_id.id),
                ('work_type_id', '=', self.work_type_id.id)
            ], limit=1)
            
            if retention_config:
                self.retention_percentage = retention_config.retention_percentage
                # Auto-calculate retention based on percentage
                self.retention = self.gross_value * (self.retention_percentage / 100)
            else:
                # البحث عن إعداد افتراضي
                default_config = self.env['retention.config'].search([
                    ('project_id', '=', False),
                    ('work_type_id', '=', False),
                    ('is_default', '=', True)
                ], limit=1)
                if default_config:
                    self.retention_percentage = default_config.retention_percentage
                    self.retention = self.gross_value * (self.retention_percentage / 100)
                else:
                    self.retention_percentage = 5.0
                    self.retention = self.gross_value * 0.05

    @api.onchange('gross_value', 'retention_percentage')
    def _onchange_retention_percentage(self):
        """Auto-calculate retention when percentage or gross value changes"""
        if self.gross_value and self.retention_percentage:
            self.retention = self.gross_value * (self.retention_percentage / 100)

    @api.constrains('work_period_from', 'work_period_to')
    def _check_work_period(self):
        for record in self:
            if record.work_period_from > record.work_period_to:
                raise ValidationError("Work period 'From' date must be before 'To' date.")

    @api.onchange('work_type_id')
    def _onchange_work_type_id(self):
        # تصفية المنتجات حسب نوع العمل
        if self.work_type_id:
            return {'domain': {'statement_line_ids': [('product_id.work_type_id', '=', self.work_type_id.id)]}}
        return {'domain': {'statement_line_ids': []}}

    def action_confirm(self):
        """Confirm the statement"""
        for record in self:
            # Update quantity tracker when confirming
            record._update_quantity_tracker()
            record.state = 'confirmed'
            record.confirmed_by = self.env.user.id
            record.confirmed_date = fields.Datetime.now()
        return True

    def action_approve(self):
        """Approve the statement"""
        for record in self:
            record.state = 'approved'
            record.approved_by = self.env.user.id
            record.approved_date = fields.Datetime.now()
            record._create_journal_entry()
        return True

    def _update_quantity_tracker(self):
        """Update quantity tracker when statement is confirmed"""
        for line in self.statement_line_ids:
            if line.current_qty > 0:
                tracker = self.env['contractor.quantity.tracker']
                tracker.update_accumulated_quantity(
                    self.project_id.id,
                    self.work_type_id.id,
                    self.contractor_id.id,
                    line.product_id.id,
                    line.current_qty
                )
    def _create_journal_entry(self):
        """Enhanced journal entry creation with proper accounting logic
        
        المنطق المحاسبي الصحيح:
        الجانب الأول (مدين):
        - إجمالي قيمة المقاولة (Total Statement Value)
        - الضرائب (Total Taxes)
        
        الجانب الثاني (دائن):
        - إجمالي الخصومات (Total Deductions)
        - صافي المستحق (Net Payable)
        
        هذا المنطق يضمن توازن القيد المحاسبي:
        مدين = إجمالي القيمة + الضرائب
        دائن = الخصومات + صافي المستحق
        """
        for record in self:
            if not record.journal_id:
                raise ValidationError("Please select a journal before approving.")
            
            if record.move_id:
                continue
            
            # Get deduction accounts
            if not record.advance_payment_account_id or not record.retention_account_id or not record.other_deductions_account_id:
                try:
                    deduction_config = self.env['deductions.config']
                    accounts = deduction_config.get_deduction_accounts(
                        project_id=record.project_id.id if record.project_id else None,
                        work_type_id=record.work_type_id.id if record.work_type_id else None
                    )
                    
                    record.advance_payment_account_id = accounts.get('advance_payment_account_id')
                    record.retention_account_id = accounts.get('retention_account_id')
                    record.other_deductions_account_id = accounts.get('other_deductions_account_id')
                except ValidationError as e:
                    raise ValidationError(f"Deduction accounts configuration error: {e}")
            
        move_vals = {
            'journal_id': record.journal_id.id,
            'date': record.statement_date,
            'ref': record.name,
            'line_ids': [],
        }
        
        # الجانب الأول: مدين - إجمالي قيمة المقاولة (Total Statement Value)
        for line in record.statement_line_ids:
            if line.current_value > 0:
                product = line.product_id
                account_id = None
                
                # تحديد الحساب المناسب
                if product.account_type == 'in' and product.in_account_id:
                    account_id = product.in_account_id.id
                elif product.account_type == 'out' and product.out_account_id:
                    account_id = product.out_account_id.id
                
                if not account_id:
                    raise ValidationError(f"Please configure account for product: {product.name}")
                
                product_line = {
                    'name': f'{product.name} - {record.name}',
                    'account_id': account_id,
                    'debit': line.current_value,  # مدين - إجمالي قيمة المقاولة
                    'credit': 0.0,
                }
                move_vals['line_ids'].append((0, 0, product_line))
        
        # الجانب الأول: مدين - الضرائب (Total Taxes)
        if record.tax_amount > 0:
            for tax in record.tax_ids:
                if tax.amount > 0:
                    tax_account = record._get_tax_account(tax)
                    if tax_account:
                        tax_value = (record.gross_value * tax.amount) / 100 if tax.amount_type == 'percent' else tax.amount
                        
                        tax_line = {
                            'name': f'Tax - {tax.name}',
                            'account_id': tax_account.id,
                            'debit': tax_value,  # مدين - الضرائب
                            'credit': 0.0,
                        }
                        move_vals['line_ids'].append((0, 0, tax_line))
        
        # الجانب الثاني: دائن - الخصومات (Total Deductions)
        if record.advance_payment_deduction > 0:
            if not record.advance_payment_account_id:
                raise ValidationError("Advance payment account is not configured!")
            
            advance_line = {
                'name': f'Advance Payment Deduction - {record.name}',
                'account_id': record.advance_payment_account_id.id,
                'debit': 0.0,
                'credit': record.advance_payment_deduction,  # دائن - خصم دفعة مقدمة
            }
            move_vals['line_ids'].append((0, 0, advance_line))
        
        if record.retention > 0:
            if not record.retention_account_id:
                raise ValidationError("Retention account is not configured!")
            
            retention_line = {
                'name': f'Retention - {record.name}',
                'account_id': record.retention_account_id.id,
                'debit': 0.0,
                'credit': record.retention,  # دائن - ضمان حسن التنفيذ
            }
            move_vals['line_ids'].append((0, 0, retention_line))
        
        if record.other_deductions > 0:
            if not record.other_deductions_account_id:
                raise ValidationError("Other deductions account is not configured!")
            
            other_deductions_line = {
                'name': f'Other Deductions - {record.name}',
                'account_id': record.other_deductions_account_id.id,
                'debit': 0.0,
                'credit': record.other_deductions,  # دائن - خصومات أخرى
            }
            move_vals['line_ids'].append((0, 0, other_deductions_line))
        
        # الجانب الثاني: دائن - صافي المستحق (Net Payable)
        if record.net_payable > 0:
            # تحديد الحساب حسب نوع المقاول
            if record.contractor_type == 'sub':
                contractor_account = record.contractor_id.property_account_payable_id.id
            else:
                contractor_account = record.contractor_id.property_account_receivable_id.id
            
            contractor_line = {
                'name': f'Contractor - {record.contractor_id.name}',
                'partner_id': record.contractor_id.id,
                'account_id': contractor_account,
                'debit': 0.0,
                'credit': record.net_payable,  # دائن - صافي المستحق
            }
            move_vals['line_ids'].append((0, 0, contractor_line))
        
        # التحقق من توازن القيد المحاسبي
        total_debit = sum(line[2].get('debit', 0.0) for line in move_vals['line_ids'])
        total_credit = sum(line[2].get('credit', 0.0) for line in move_vals['line_ids'])
        
        _logger = logging.getLogger(__name__)
        _logger.info(f"Statement: {record.name}")
        _logger.info(f"Total Statement Value: {record.gross_value}")
        _logger.info(f"Total Taxes: {record.tax_amount}")
        _logger.info(f"Total Deductions: {record.advance_payment_deduction + record.retention + record.other_deductions}")
        _logger.info(f"Net Payable: {record.net_payable}")
        _logger.info(f"Total Debit: {total_debit}")
        _logger.info(f"Total Credit: {total_credit}")
        
        # التحقق من صحة المعادلة المحاسبية
        expected_debit = record.gross_value + record.tax_amount
        expected_credit = (record.advance_payment_deduction + record.retention + record.other_deductions) + record.net_payable
        
        if abs(expected_debit - expected_credit) > 0.01:
            raise ValidationError(
                f"Accounting equation is not balanced!\n"
                f"Expected: (Statement Value + Taxes) = (Deductions + Net Payable)\n"
                f"Expected: ({record.gross_value} + {record.tax_amount}) = ({record.advance_payment_deduction + record.retention + record.other_deductions} + {record.net_payable})\n"
                f"Expected: {expected_debit} = {expected_credit}\n"
                f"Difference: {abs(expected_debit - expected_credit)}"
            )
        
        if abs(total_debit - total_credit) > 0.01:
            raise ValidationError(f"Journal entry is not balanced! Debit: {total_debit}, Credit: {total_credit}")
        
        # إنشاء القيد
        if move_vals['line_ids']:
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            record.move_id = move.id
    def _get_tax_account(self, tax):
        """Get the correct tax account from tax configuration"""
        # البحث عن الحساب المناسب من إعدادات الضريبة
        if tax.invoice_repartition_line_ids:
            for line in tax.invoice_repartition_line_ids:
                if line.repartition_type == 'tax' and line.account_id:
                    return line.account_id
        
        # إذا لم يوجد حساب مُعرف، استخدم الحساب الافتراضي للضرائب
        company = self.env.company
        if hasattr(company, 'account_sale_tax_id') and company.account_sale_tax_id:
            return company.account_sale_tax_id
        
        # البحث عن حساب ضرائب عام
        tax_account = self.env['account.account'].search([
            ('code', 'ilike', 'tax'),
            ('company_id', '=', company.id)
        ], limit=1)
        
        if not tax_account:
            raise ValidationError(f"No tax account found for tax: {tax.name}. Please configure tax accounts properly.")
        
        return tax_account

    def action_reset_to_draft(self):
        """Reset statement to draft"""
        for record in self:
            if record.state == 'paid':
                raise ValidationError("Cannot reset a paid statement to draft!")
            
            # إذا كان المستخلص مؤكد، نحتاج لتحديث quantity tracker
            if record.state == 'confirmed':
                record._reverse_quantity_tracker()
            
            record.state = 'draft'
        return True

    def _reverse_quantity_tracker(self):
        """Reverse quantity tracker when resetting to draft"""
        for line in self.statement_line_ids:
            if line.current_qty > 0:
                tracker = self.env['contractor.quantity.tracker']
                tracker.update_accumulated_quantity(
                    self.project_id.id,
                    self.work_type_id.id,
                    self.contractor_id.id,
                    line.product_id.id,
                    -line.current_qty  # سالب لإلغاء الكمية
                )

    def action_mark_as_paid(self):
        """Mark statement as paid and create payment record"""
        for record in self:
            if record.state != 'approved':
                raise ValidationError("Only approved statements can be marked as paid!")
            
            if not record.payment_method_id:
                raise ValidationError("Please define a payment method line on your payment.")
            
            # Create payment record
            payment_vals = {
                'payment_type': 'outbound' if record.contractor_type == 'sub' else 'inbound',
                'partner_id': record.contractor_id.id,
                'amount': record.net_payable,
                'journal_id': record.payment_method_id.journal_id.id,
                'date': fields.Date.today(),
                'ref': f'Payment for {record.name}',
                'partner_type': 'supplier' if record.contractor_type == 'sub' else 'customer',
            }
            
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()
            
            record.payment_id = payment.id
            record.state = 'paid'
            record.paid_by = self.env.user.id
            record.paid_date = fields.Datetime.now()
        return True

    def unlink(self):
        """Override unlink to handle quantity tracker and prevent deletion of approved statements"""
        for record in self:
            if record.state in ['approved', 'paid']:
                raise ValidationError("You cannot delete an approved or paid statement because it has generated accounting entries.")
            if record.state == 'confirmed':
                record._reverse_quantity_tracker()
        return super(ContractorStatement, self).unlink()


class ContractorStatementLine(models.Model):
    _name = 'contractor.statement.line'
    _description = 'Contractor Statement Line'

    statement_id = fields.Many2one('contractor.statement', string='Statement', required=True, ondelete='cascade')
    sequence = fields.Integer(string='#', default=1)
    product_id = fields.Many2one('contractor.product', string='Product', required=True)
    description = fields.Char(string='Item Description', related='product_id.name', store=True)
    unit = fields.Char(string='Unit', related='product_id.unit', store=True)
    
    # Quantities
    contract_qty = fields.Float(string='Contract Qty', compute='_compute_contract_qty', store=True)
    prev_qty = fields.Float(string='Previous Qty', compute='_compute_prev_qty', store=True)
    current_qty = fields.Float(string='Current Qty', required=True)
    total_qty = fields.Float(string='Total Qty', compute='_compute_total_qty', store=True)
    progress_percent = fields.Float(string='Progress %', compute='_compute_progress', store=True)
    
    # Prices
    unit_price = fields.Float(string='Unit Price', required=True)
    current_value = fields.Float(string='Current Value', compute='_compute_current_value', store=True)
    total_value = fields.Float(string='Total Value', compute='_compute_total_value', store=True)

    @api.depends('statement_id.project_id', 'statement_id.work_type_id', 'statement_id.contractor_id', 'product_id')
    def _compute_contract_qty(self):
        for line in self:
            if line.statement_id.project_id and line.statement_id.work_type_id and line.statement_id.contractor_id and line.product_id:
                contract_qty_record = self.env['contract.quantity'].search([
                    ('project_id', '=', line.statement_id.project_id.id),
                    ('work_type_id', '=', line.statement_id.work_type_id.id),
                    ('contractor_id', '=', line.statement_id.contractor_id.id),
                    ('product_id', '=', line.product_id.id)
                ], limit=1)
                line.contract_qty = contract_qty_record.quantity if contract_qty_record else 0.0
            else:
                line.contract_qty = 0.0

    @api.depends('statement_id.project_id', 'statement_id.work_type_id', 'statement_id.contractor_id', 'product_id', 'statement_id.statement_date')
    def _compute_prev_qty(self):
        for line in self:
            line.prev_qty = line._get_previous_quantity()

    def _get_previous_quantity(self):
        """Get previous quantity from database table or computed from previous statements"""
        # First, check if we have a record in the new quantity tracker table
        tracker = self.env['contractor.quantity.tracker'].search([
            ('project_id', '=', self.statement_id.project_id.id),
            ('work_type_id', '=', self.statement_id.work_type_id.id),
            ('contractor_id', '=', self.statement_id.contractor_id.id),
            ('product_id', '=', self.product_id.id)
        ], limit=1)
        
        if tracker:
            return tracker.accumulated_quantity
        else:
            # If no tracker record, compute from previous statements
            if self.statement_id.project_id and self.statement_id.work_type_id and self.statement_id.contractor_id and self.product_id:
                domain = [
                    ('statement_id.project_id', '=', self.statement_id.project_id.id),
                    ('statement_id.work_type_id', '=', self.statement_id.work_type_id.id),
                    ('statement_id.contractor_id', '=', self.statement_id.contractor_id.id),
                    ('product_id', '=', self.product_id.id),
                    ('statement_id.statement_date', '<', self.statement_id.statement_date),
                    ('statement_id.state', '!=', 'draft')
                ]
                previous_lines = self.search(domain)
                return sum(previous_lines.mapped('current_qty'))
            else:
                return 0.0

    @api.depends('prev_qty', 'current_qty')
    def _compute_total_qty(self):
        for line in self:
            line.total_qty = line.prev_qty + line.current_qty

    @api.depends('total_qty', 'contract_qty')
    def _compute_progress(self):
        for line in self:
            if line.contract_qty > 0:
                line.progress_percent = (line.total_qty / line.contract_qty) * 100
            else:
                line.progress_percent = 0.0

    @api.depends('current_qty', 'unit_price')
    def _compute_current_value(self):
        for line in self:
            line.current_value = line.current_qty * line.unit_price

    @api.depends('total_qty', 'unit_price')
    def _compute_total_value(self):
        for line in self:
            line.total_value = line.total_qty * line.unit_price

    @api.constrains('current_qty', 'contract_qty', 'total_qty')
    def _check_quantities(self):
        for line in self:
            if line.total_qty > line.contract_qty:
                raise ValidationError(f"Total quantity ({line.total_qty}) cannot exceed contract quantity ({line.contract_qty}) for item: {line.description}")


class ContractorQuantityTracker(models.Model):
    """Model to track accumulated quantities for better performance"""
    _name = 'contractor.quantity.tracker'
    _description = 'Contractor Quantity Tracker'
    _rec_name = 'display_name'

    project_id = fields.Many2one('project.config', string='Project', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    contractor_id = fields.Many2one('res.partner', string='Contractor', required=True)
    product_id = fields.Many2one('contractor.product', string='Product', required=True)
    accumulated_quantity = fields.Float(string='Accumulated Quantity', default=0.0)
    last_updated = fields.Datetime(string='Last Updated', default=fields.Datetime.now)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('project_id', 'work_type_id', 'contractor_id', 'product_id')
    def _compute_display_name(self):
        for record in self:
            if record.project_id and record.work_type_id and record.contractor_id and record.product_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.contractor_id.name} - {record.product_id.name}"
            else:
                record.display_name = "Quantity Tracker"

    def update_accumulated_quantity(self, project_id, work_type_id, contractor_id, product_id, quantity_to_add):
        """Update or create tracker record"""
        tracker = self.search([
            ('project_id', '=', project_id),
            ('work_type_id', '=', work_type_id),
            ('contractor_id', '=', contractor_id),
            ('product_id', '=', product_id)
        ], limit=1)
        
        if tracker:
            tracker.accumulated_quantity += quantity_to_add
            tracker.last_updated = fields.Datetime.now()
            
            # تنظيف السجلات التي تحتوي على كمية صفر
            if tracker.accumulated_quantity == 0:
                tracker.unlink()
        else:
            if quantity_to_add > 0:  # إنشاء سجل جديد فقط إذا كانت الكمية أكبر من صفر
                self.create({
                    'project_id': project_id,
                    'work_type_id': work_type_id,
                    'contractor_id': contractor_id,
                    'product_id': product_id,
                    'accumulated_quantity': quantity_to_add,
                    'last_updated': fields.Datetime.now()
                })

    _sql_constraints = [
        ('unique_tracker', 'unique(project_id, work_type_id, contractor_id, product_id)', 
         'Quantity tracker must be unique per project, work type, contractor, and product!'),
    ]


class ContractQuantity(models.Model):
    _name = 'contract.quantity'
    _description = 'Contract Quantity'
    _rec_name = 'display_name'

    project_id = fields.Many2one('project.config', string='Project', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    contractor_id = fields.Many2one('res.partner', string='Contractor', domain="[('is_company', '=', True)]", required=True)
    product_id = fields.Many2one('contractor.product', string='Product', required=True)
    quantity = fields.Float(string='Contract Quantity', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('project_id', 'work_type_id', 'contractor_id', 'product_id')
    def _compute_display_name(self):
        for record in self:
            if record.project_id and record.work_type_id and record.contractor_id and record.product_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.contractor_id.name} - {record.product_id.name}"
            else:
                record.display_name = "Contract Quantity"

    @api.onchange('work_type_id')
    def _onchange_work_type_id(self):
        if self.work_type_id:
            return {'domain': {'product_id': [('work_type_id', '=', self.work_type_id.id)]}}
        return {'domain': {'product_id': []}}

    _sql_constraints = [
        ('unique_contract_qty', 'unique(project_id, work_type_id, contractor_id, product_id)', 
         'Contract quantity must be unique per project, work type, contractor, and product!'),
    ]
class RetentionConfig(models.Model):
    _name = 'retention.config'
    _description = 'Retention Configuration'
    _rec_name = 'display_name'

    project_id = fields.Many2one('project.config', string='Project')
    work_type_id = fields.Many2one('work.type.config', string='Work Type')
    retention_percentage = fields.Float(string='Retention Percentage (%)', required=True, default=5.0)
    is_default = fields.Boolean(string='Is Default', default=False)
    active = fields.Boolean(string='Active', default=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('project_id', 'work_type_id', 'is_default')
    def _compute_display_name(self):
        for record in self:
            if record.is_default:
                record.display_name = f"Default - {record.retention_percentage}%"
            elif record.project_id and record.work_type_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.retention_percentage}%"
            elif record.project_id:
                record.display_name = f"{record.project_id.name} - {record.retention_percentage}%"
            elif record.work_type_id:
                record.display_name = f"{record.work_type_id.name} - {record.retention_percentage}%"
            else:
                record.display_name = f"Retention Config - {record.retention_percentage}%"

    @api.constrains('is_default')
    def _check_default_unique(self):
        for record in self:
            if record.is_default:
                existing_default = self.search([
                    ('is_default', '=', True),
                    ('id', '!=', record.id)
                ])
                if existing_default:
                    raise ValidationError("Only one default retention configuration is allowed!")

    _sql_constraints = [
        ('unique_project_work_type', 'unique(project_id, work_type_id)', 
         'Retention configuration must be unique per project and work type!'),
    ]


class ProjectConfig(models.Model):
    _name = 'project.config'
    _description = 'Project Configuration'
    
    name = fields.Char(string='Project Name', required=True)
    code = fields.Char(string='Project Code', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Project code must be unique!'),
    ]


class WorkTypeConfig(models.Model):
    _name = 'work.type.config'
    _description = 'Work Type Configuration'
    
    name = fields.Char(string='Work Type', required=True)
    code = fields.Char(string='Work Type Code', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Work type code must be unique!'),
    ]

class DeductionsConfig(models.Model):
    _name = 'deductions.config'
    _description = 'Deductions Configuration'
    _rec_name = 'display_name'

    # Configuration Info
    name = fields.Char(string='Configuration Name', required=True, default='Default Deductions Configuration')
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Is Default Configuration', default=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    # Deduction Accounts
    advance_payment_account_id = fields.Many2one(
        'account.account', 
        string='Advance Payment Account',
        domain="[('company_id', '=', company_id)]",
        help="Account used for advance payment deductions"
    )
    
    retention_account_id = fields.Many2one(
        'account.account', 
        string='Retention Account',
        domain="[('company_id', '=', company_id)]",
        help="Account used for retention/warranty deductions"
    )
    
    retention_percentage = fields.Float(
        string='Retention %', 
        default=5.0,
        help="Default percentage for retention deductions"
    )
    
    other_deductions_account_id = fields.Many2one(
        'account.account', 
        string='Other Deductions Account',
        domain="[('company_id', '=', company_id)]",
        help="Account used for other miscellaneous deductions"
    )
    
    # Optional: Project/Work Type Specific
    project_id = fields.Many2one('project.config', string='Specific Project', help="Leave empty for general configuration")
    work_type_id = fields.Many2one('work.type.config', string='Specific Work Type', help="Leave empty for general configuration")
    
    # Display Name
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    @api.depends('name', 'project_id', 'work_type_id', 'is_default')
    def _compute_display_name(self):
        for record in self:
            if record.is_default:
                record.display_name = f"Default - {record.name}"
            elif record.project_id and record.work_type_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.name}"
            elif record.project_id:
                record.display_name = f"{record.project_id.name} - {record.name}"
            elif record.work_type_id:
                record.display_name = f"{record.work_type_id.name} - {record.name}"
            else:
                record.display_name = record.name

    @api.constrains('is_default')
    def _check_default_unique(self):
        for record in self:
            if record.is_default:
                existing_default = self.search([
                    ('is_default', '=', True),
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id)
                ])
                if existing_default:
                    raise ValidationError("Only one default deductions configuration is allowed per company!")

    def get_deduction_accounts(self, project_id=None, work_type_id=None):
        """
        Get the appropriate deduction accounts based on project and work type
        Returns a dictionary with account IDs and retention percentage
        """
        # Search for specific configuration first
        config = None
        
        if project_id and work_type_id:
            config = self.search([
                ('project_id', '=', project_id),
                ('work_type_id', '=', work_type_id),
                ('active', '=', True)
            ], limit=1)
        
        if not config and project_id:
            config = self.search([
                ('project_id', '=', project_id),
                ('work_type_id', '=', False),
                ('active', '=', True)
            ], limit=1)
        
        if not config and work_type_id:
            config = self.search([
                ('project_id', '=', False),
                ('work_type_id', '=', work_type_id),
                ('active', '=', True)
            ], limit=1)
        
        # Fall back to default configuration
        if not config:
            config = self.search([
                ('is_default', '=', True),
                ('active', '=', True)
            ], limit=1)
        
        if not config:
            raise ValidationError("No deductions configuration found! Please set up at least one default configuration.")
        
        return {
            'advance_payment_account_id': config.advance_payment_account_id.id if config.advance_payment_account_id else False,
            'retention_account_id': config.retention_account_id.id if config.retention_account_id else False,
            'other_deductions_account_id': config.other_deductions_account_id.id if config.other_deductions_account_id else False,
            'retention_percentage': config.retention_percentage,
        }

    _sql_constraints = [
        ('unique_project_work_type', 'unique(project_id, work_type_id, company_id)', 
         'Deductions configuration must be unique per project, work type, and company!'),
    ]


class ContractorProduct(models.Model):
    _name = 'contractor.product'
    _description = 'Contractor Product'
    
    name = fields.Char(string='Product Name', required=True)
    code = fields.Char(string='Product Code', required=True)
    unit = fields.Char(string='Unit of Measure', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    # Account Configuration
    account_type = fields.Selection([
        ('in', 'In'),
        ('out', 'Out')
    ], string='Account Type', required=True, default='in')
    in_account_id = fields.Many2one('account.account', string='In Account')
    out_account_id = fields.Many2one('account.account', string='Out Account')
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Product code must be unique!'),
    ]
# إضافة هذا الاستيراد في بداية الملف
from odoo.tools.misc import xlwt
import base64
import io

# إضافة هذه الحقول في نموذج ContractorStatement
xls_file = fields.Binary('Excel File')
xls_filename = fields.Char('Excel Filename')

# إضافة هذه الدالة في نموذج ContractorStatement
def action_export_excel(self):
    """Export statement to Excel"""
    for record in self:
        workbook = xlwt.Workbook(encoding='utf-8')
        worksheet = workbook.add_sheet('Contractor Statement')
        
        # Styles
        header_style = xlwt.easyxf('font: bold on, height 200; align: horiz center, vert center; borders: left thin, right thin, top thin, bottom thin')
        cell_style = xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin')
        number_style = xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin; align: horiz right')
        
        # Header
        worksheet.write_merge(0, 0, 0, 10, 'Contractor Statement: ' + record.name, header_style)
        
        # Basic Info
        worksheet.write(2, 0, 'Project:', cell_style)
        worksheet.write(2, 1, record.project_id.name, cell_style)
        worksheet.write(3, 0, 'Work Type:', cell_style)
        worksheet.write(3, 1, record.work_type_id.name, cell_style)
        worksheet.write(4, 0, 'Contractor:', cell_style)
        worksheet.write(4, 1, record.contractor_id.name, cell_style)
        worksheet.write(5, 0, 'Statement Date:', cell_style)
        worksheet.write(5, 1, str(record.statement_date), cell_style)
        
        # Column Headers
        row = 7
        headers = ['#', 'Product', 'Description', 'Unit', 'Contract Qty', 'Previous Qty', 'Current Qty', 'Total Qty', 'Progress %', 'Unit Price', 'Current Value', 'Total Value']
        for col, header in enumerate(headers):
            worksheet.write(row, col, header, header_style)
        
        # Statement Lines
        row += 1
        for i, line in enumerate(record.statement_line_ids):
            worksheet.write(row, 0, i+1, cell_style)
            worksheet.write(row, 1, line.product_id.name, cell_style)
            worksheet.write(row, 2, line.description, cell_style)
            worksheet.write(row, 3, line.unit, cell_style)
            worksheet.write(row, 4, line.contract_qty, number_style)
            worksheet.write(row, 5, line.prev_qty, number_style)
            worksheet.write(row, 6, line.current_qty, number_style)
            worksheet.write(row, 7, line.total_qty, number_style)
            worksheet.write(row, 8, line.progress_percent, number_style)
            worksheet.write(row, 9, line.unit_price, number_style)
            worksheet.write(row, 10, line.current_value, number_style)
            worksheet.write(row, 11, line.total_value, number_style)
            row += 1
        
        # Summary
        row += 2
        worksheet.write(row, 9, 'Gross Value:', cell_style)
        worksheet.write(row, 10, record.gross_value, number_style)
        row += 1
        worksheet.write(row, 9, 'Tax Amount:', cell_style)
        worksheet.write(row, 10, record.tax_amount, number_style)
        row += 1
        worksheet.write(row, 9, 'Advance Payment Deduction:', cell_style)
        worksheet.write(row, 10, record.advance_payment_deduction, number_style)
        row += 1
        worksheet.write(row, 9, 'Retention:', cell_style)
        worksheet.write(row, 10, record.retention, number_style)
        row += 1
        worksheet.write(row, 9, 'Other Deductions:', cell_style)
        worksheet.write(row, 10, record.other_deductions, number_style)
        row += 1
        worksheet.write(row, 9, 'Total Deductions:', cell_style)
        worksheet.write(row, 10, record.total_deductions, number_style)
        row += 1
        worksheet.write(row, 9, 'Net Payable:', header_style)
        worksheet.write(row, 10, record.net_payable, header_style)
        
        # Save to binary field
        fp = io.BytesIO()
        workbook.save(fp)
        record.xls_file = base64.b64encode(fp.getvalue())
        record.xls_filename = f"{record.name}.xls"
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=contractor.statement&id={record.id}&field=xls_file&filename_field=xls_filename&download=true',
            'target': 'self',
        }





class ContractorQuantityTracker(models.Model):
    """Model to track accumulated quantities for better performance"""
    _name = 'contractor.quantity.tracker'
    _description = 'Contractor Quantity Tracker'
    _rec_name = 'display_name'

    project_id = fields.Many2one('project.config', string='Project', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    contractor_id = fields.Many2one('res.partner', string='Contractor', required=True)
    product_id = fields.Many2one('contractor.product', string='Product', required=True)
    accumulated_quantity = fields.Float(string='Accumulated Quantity', default=0.0)
    last_updated = fields.Datetime(string='Last Updated', default=fields.Datetime.now)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('project_id', 'work_type_id', 'contractor_id', 'product_id')
    def _compute_display_name(self):
        for record in self:
            if record.project_id and record.work_type_id and record.contractor_id and record.product_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.contractor_id.name} - {record.product_id.name}"
            else:
                record.display_name = "Quantity Tracker"

    def update_accumulated_quantity(self, project_id, work_type_id, contractor_id, product_id, quantity_to_add):
        """Update or create tracker record"""
        tracker = self.search([
            ('project_id', '=', project_id),
            ('work_type_id', '=', work_type_id),
            ('contractor_id', '=', contractor_id),
            ('product_id', '=', product_id)
        ], limit=1)
        
        if tracker:
            tracker.accumulated_quantity += quantity_to_add
            tracker.last_updated = fields.Datetime.now()
            
            # تنظيف السجلات التي تحتوي على كمية صفر
            if tracker.accumulated_quantity == 0:
                tracker.unlink()
        else:
            if quantity_to_add > 0:  # إنشاء سجل جديد فقط إذا كانت الكمية أكبر من صفر
                self.create({
                    'project_id': project_id,
                    'work_type_id': work_type_id,
                    'contractor_id': contractor_id,
                    'product_id': product_id,
                    'accumulated_quantity': quantity_to_add,
                    'last_updated': fields.Datetime.now()
                })

    _sql_constraints = [
        ('unique_tracker', 'unique(project_id, work_type_id, contractor_id, product_id)', 
         'Quantity tracker must be unique per project, work type, contractor, and product!'),
    ]


class ContractQuantity(models.Model):
    _name = 'contract.quantity'
    _description = 'Contract Quantity'
    _rec_name = 'display_name'

    project_id = fields.Many2one('project.config', string='Project', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    contractor_id = fields.Many2one('res.partner', string='Contractor', domain="[('is_company', '=', True)]", required=True)
    product_id = fields.Many2one('contractor.product', string='Product', required=True)
    quantity = fields.Float(string='Contract Quantity', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('project_id', 'work_type_id', 'contractor_id', 'product_id')
    def _compute_display_name(self):
        for record in self:
            if record.project_id and record.work_type_id and record.contractor_id and record.product_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.contractor_id.name} - {record.product_id.name}"
            else:
                record.display_name = "Contract Quantity"

    @api.onchange('work_type_id')
    def _onchange_work_type_id(self):
        if self.work_type_id:
            return {'domain': {'product_id': [('work_type_id', '=', self.work_type_id.id)]}}
        return {'domain': {'product_id': []}}

    _sql_constraints = [
        ('unique_contract_qty', 'unique(project_id, work_type_id, contractor_id, product_id)', 
         'Contract quantity must be unique per project, work type, contractor, and product!'),
    ]
class RetentionConfig(models.Model):
    _name = 'retention.config'
    _description = 'Retention Configuration'
    _rec_name = 'display_name'

    project_id = fields.Many2one('project.config', string='Project')
    work_type_id = fields.Many2one('work.type.config', string='Work Type')
    retention_percentage = fields.Float(string='Retention Percentage (%)', required=True, default=5.0)
    is_default = fields.Boolean(string='Is Default', default=False)
    active = fields.Boolean(string='Active', default=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('project_id', 'work_type_id', 'is_default')
    def _compute_display_name(self):
        for record in self:
            if record.is_default:
                record.display_name = f"Default - {record.retention_percentage}%"
            elif record.project_id and record.work_type_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.retention_percentage}%"
            elif record.project_id:
                record.display_name = f"{record.project_id.name} - {record.retention_percentage}%"
            elif record.work_type_id:
                record.display_name = f"{record.work_type_id.name} - {record.retention_percentage}%"
            else:
                record.display_name = f"Retention Config - {record.retention_percentage}%"

    @api.constrains('is_default')
    def _check_default_unique(self):
        for record in self:
            if record.is_default:
                existing_default = self.search([
                    ('is_default', '=', True),
                    ('id', '!=', record.id)
                ])
                if existing_default:
                    raise ValidationError("Only one default retention configuration is allowed!")

    _sql_constraints = [
        ('unique_project_work_type', 'unique(project_id, work_type_id)', 
         'Retention configuration must be unique per project and work type!'),
    ]


class ProjectConfig(models.Model):
    _name = 'project.config'
    _description = 'Project Configuration'
    
    name = fields.Char(string='Project Name', required=True)
    code = fields.Char(string='Project Code', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Project code must be unique!'),
    ]


class WorkTypeConfig(models.Model):
    _name = 'work.type.config'
    _description = 'Work Type Configuration'
    
    name = fields.Char(string='Work Type', required=True)
    code = fields.Char(string='Work Type Code', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Work type code must be unique!'),
    ]

class DeductionsConfig(models.Model):
    _name = 'deductions.config'
    _description = 'Deductions Configuration'
    _rec_name = 'display_name'

    # Configuration Info
    name = fields.Char(string='Configuration Name', required=True, default='Default Deductions Configuration')
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Is Default Configuration', default=False)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    
    # Deduction Accounts
    advance_payment_account_id = fields.Many2one(
        'account.account', 
        string='Advance Payment Account',
        domain="[('company_id', '=', company_id)]",
        help="Account used for advance payment deductions"
    )
    
    retention_account_id = fields.Many2one(
        'account.account', 
        string='Retention Account',
        domain="[('company_id', '=', company_id)]",
        help="Account used for retention/warranty deductions"
    )
    
    retention_percentage = fields.Float(
        string='Retention %', 
        default=5.0,
        help="Default percentage for retention deductions"
    )
    
    other_deductions_account_id = fields.Many2one(
        'account.account', 
        string='Other Deductions Account',
        domain="[('company_id', '=', company_id)]",
        help="Account used for other miscellaneous deductions"
    )
    
    # Optional: Project/Work Type Specific
    project_id = fields.Many2one('project.config', string='Specific Project', help="Leave empty for general configuration")
    work_type_id = fields.Many2one('work.type.config', string='Specific Work Type', help="Leave empty for general configuration")
    
    # Display Name
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    @api.depends('name', 'project_id', 'work_type_id', 'is_default')
    def _compute_display_name(self):
        for record in self:
            if record.is_default:
                record.display_name = f"Default - {record.name}"
            elif record.project_id and record.work_type_id:
                record.display_name = f"{record.project_id.name} - {record.work_type_id.name} - {record.name}"
            elif record.project_id:
                record.display_name = f"{record.project_id.name} - {record.name}"
            elif record.work_type_id:
                record.display_name = f"{record.work_type_id.name} - {record.name}"
            else:
                record.display_name = record.name

    @api.constrains('is_default')
    def _check_default_unique(self):
        for record in self:
            if record.is_default:
                existing_default = self.search([
                    ('is_default', '=', True),
                    ('id', '!=', record.id),
                    ('company_id', '=', record.company_id.id)
                ])
                if existing_default:
                    raise ValidationError("Only one default deductions configuration is allowed per company!")

    def get_deduction_accounts(self, project_id=None, work_type_id=None):
        """
        Get the appropriate deduction accounts based on project and work type
        Returns a dictionary with account IDs and retention percentage
        """
        # Search for specific configuration first
        config = None
        
        if project_id and work_type_id:
            config = self.search([
                ('project_id', '=', project_id),
                ('work_type_id', '=', work_type_id),
                ('active', '=', True)
            ], limit=1)
        
        if not config and project_id:
            config = self.search([
                ('project_id', '=', project_id),
                ('work_type_id', '=', False),
                ('active', '=', True)
            ], limit=1)
        
        if not config and work_type_id:
            config = self.search([
                ('project_id', '=', False),
                ('work_type_id', '=', work_type_id),
                ('active', '=', True)
            ], limit=1)
        
        # Fall back to default configuration
        if not config:
            config = self.search([
                ('is_default', '=', True),
                ('active', '=', True)
            ], limit=1)
        
        if not config:
            raise ValidationError("No deductions configuration found! Please set up at least one default configuration.")
        
        return {
            'advance_payment_account_id': config.advance_payment_account_id.id if config.advance_payment_account_id else False,
            'retention_account_id': config.retention_account_id.id if config.retention_account_id else False,
            'other_deductions_account_id': config.other_deductions_account_id.id if config.other_deductions_account_id else False,
            'retention_percentage': config.retention_percentage,
        }

    _sql_constraints = [
        ('unique_project_work_type', 'unique(project_id, work_type_id, company_id)', 
         'Deductions configuration must be unique per project, work type, and company!'),
    ]


class ContractorProduct(models.Model):
    _name = 'contractor.product'
    _description = 'Contractor Product'
    
    name = fields.Char(string='Product Name', required=True)
    code = fields.Char(string='Product Code', required=True)
    unit = fields.Char(string='Unit of Measure', required=True)
    work_type_id = fields.Many2one('work.type.config', string='Work Type', required=True)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    
    # Account Configuration
    account_type = fields.Selection([
        ('in', 'In'),
        ('out', 'Out')
    ], string='Account Type', required=True, default='in')
    in_account_id = fields.Many2one('account.account', string='In Account')
    out_account_id = fields.Many2one('account.account', string='Out Account')
    
    _sql_constraints = [
        ('code_unique', 'unique(code)', 'Product code must be unique!'),]