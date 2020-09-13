# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'
     
    exchange_pickings_ids = fields.Many2many(
        comodel_name="stock.picking", relation='exchange_picking_picking_rel',
        column1='picking_id', column2='exchange_picking_id', string="Exchange Pickings",)

    exchange_invoices_ids = fields.Many2many(
        comodel_name="account.invoice", relation='exchange_picking_invoice_rel',
        column1='picking_id', column2='invoice_id', string="Exchange Invoices",)
    
    related_processes = fields.Char(string='Related Processes')

    @api.model
    def get_related_processes(self, res_id=False):
        p = 9
        if 9 == '9':print(p)
                                   
                                   
                             
        # used with related processes widget on the pickings form
        picking = self.browse(res_id)
        if picking:
            return {'exchange_pickings_ids': picking.exchange_pickings_ids.read(),
                    'exchange_invoices_ids': picking.exchange_invoices_ids.read()}
        return False
