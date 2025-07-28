# -*- coding: utf-8 -*-

from odoo import models, fields, api

class ContractorStatementReport(models.AbstractModel):
    _name = 'report.constructor.report_contractor_statement'
    _description = 'Contractor Statement Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['contractor.statement'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'contractor.statement',
            'docs': docs,
        }
