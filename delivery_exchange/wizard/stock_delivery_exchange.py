# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_round, float_is_zero


class DeliveryExchangeLine(models.TransientModel):
    _name = "stock.delivery.exchange.line"
    _rec_name = 'product_id'
    _description = 'Exchange Picking Line'

    product_id = fields.Many2one('product.product', string="Product", required=True)
    quantity = fields.Float("Quantity", digits=dp.get_precision(
        'Product Unit of Measure'), required=True)
    price_unit = fields.Float(string='Unit Price', required=True,
                              digits=dp.get_precision('Product Price'))
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
                             readonly=False)
    wizard_id = fields.Many2one('stock.delivery.exchange', string="Wizard")
    move_id = fields.Many2one('stock.move', "Move")
    purchase_line_id = fields.Many2one(comodel_name='purchase.order.line',
                                       string='Purchase Order Line', ondelete='set null')

    sale_line_id = fields.Many2one(comodel_name='sale.order.line', string='Sale Line',
                                   ondelete='set null')

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        Change uom_id when a new product changed
        """
        if self.product_id:
            self.uom_id = self.product_id.uom_id.id
        else:
            self.uom_id = False


class DeliveryExchange(models.TransientModel):
    _name = 'stock.delivery.exchange'
    _description = 'Exchange Picking'

    picking_id = fields.Many2one('stock.picking')
    product_exchange_moves = fields.One2many('stock.delivery.exchange.line', 'wizard_id', 'Moves')
    move_dest_exists = fields.Boolean('Chained Move Exists', readonly=True)
    original_location_id = fields.Many2one('stock.location')
    parent_location_id = fields.Many2one('stock.location')
    location_id = fields.Many2one(
        'stock.location', 'Exchange Location',
        domain="['|', ('id', '=', original_location_id), ('return_location', '=', True)]")

    partner_id = fields.Many2one(
        'res.partner', string='Customer',
        help="You can find a customer by its Name, TIN, Email or Internal Reference.")

    product_added = fields.Boolean(string='A new Product added')

    @api.onchange('product_exchange_moves')
    def _onchange_product_exchange_moves(self):
        """
        Change product_added when a new product added so the user must enter a partner
        or removed
        """
        if any(self.product_exchange_moves.filtered(lambda m: not m.move_id)):
            self.product_added = True
        else:
            self.product_added = False

    def _prepare_product_exchange_move(self, move):
        # the default data for the new proudct_exchange_move

        quantity = move.product_qty

        # get the exchange moves created form this move
        exchange_moves = move.move_dest_ids.filtered(
            lambda m: m.state in ['partially_available', 'assigned', 'done'] and m.location_id.id ==
            move.location_dest_id.id and move.location_id.id == m.location_dest_id.id)

        if exchange_moves:
            quantity -= sum([x.product_uom._compute_quantity(x.product_uom_qty, x.product_uom)
                             for x in exchange_moves])

        quantity = float_round(quantity, precision_rounding=move.product_uom.rounding)

        price_unit = 0.0

        if move.purchase_line_id:
            price_unit = move.purchase_line_id.price_unit

        if move.sale_line_id:
            price_unit = move.sale_line_id.price_unit

        vals = {'product_id': move.product_id.id, 'quantity': quantity, 'move_id': move.id,
                'uom_id': move.product_uom.id,
                'purchase_line_id': move.purchase_line_id and move.purchase_line_id.id or False,
                'sale_line_id': move.sale_line_id and move.sale_line_id.id or False,
                'price_unit': price_unit}
        return vals

    @api.model
    def default_get(self, fields):
        if len(self.env.context.get('active_ids', list())) > 1:
            raise UserError(_("You may only return one picking at a time."))
        res = super(DeliveryExchange, self).default_get(fields)

        move_dest_exists = False
        product_exchange_moves = []
        picking = self.env['stock.picking'].browse(self.env.context.get('active_id'))
        if picking:
            res.update({'picking_id': picking.id})
            if picking.state != 'done':
                raise UserError(_("You may only return Done pickings."))
            for move in picking.move_lines:
                if move.scrapped:
                    continue
                if move.move_dest_ids:
                    move_dest_exists = True

                product_exchange_moves.append(
                    (0, 0,
                     self._prepare_product_exchange_move(move)))

            if 'product_exchange_moves' in fields:
                res.update({'product_exchange_moves': product_exchange_moves})
            if 'move_dest_exists' in fields:
                res.update({'move_dest_exists': move_dest_exists})
            if 'parent_location_id' in fields and picking.location_id.usage == 'internal':
                res.update(
                    {'parent_location_id': picking.picking_type_id.warehouse_id and picking.picking_type_id.warehouse_id.view_location_id.id or picking.location_id.location_id.id})
            if 'location_id' in fields:
                location_id = picking.location_id.id
                if picking.picking_type_id.return_picking_type_id.default_location_dest_id.return_location:
                    location_id = picking.picking_type_id.return_picking_type_id.default_location_dest_id.id
                res['location_id'] = location_id
        return res

    def _prepare_move_default_values(self, return_line, new_picking):
        vals = {
            'product_id': return_line.product_id.id,
            'product_uom_qty': return_line.quantity,
            'product_uom': return_line.product_id.uom_id.id,
            'picking_id': new_picking.id,
            'state': 'draft',
            'date_expected': fields.Datetime.now(),
            'location_id': return_line.move_id.location_dest_id.id,
            'location_dest_id': self.location_id.id or return_line.move_id.location_id.id,
            'picking_type_id': new_picking.picking_type_id.id,
            'warehouse_id': self.picking_id.picking_type_id.warehouse_id.id,
            'origin_returned_move_id': return_line.move_id.id,
            'procure_method': 'make_to_stock',
            'to_refund': True,
        }
        return vals

    def _prepare_new_picking_values(self, picking_type_id):
        # the data for the new picking
        vals = {
            'move_lines': [],
            'picking_type_id': picking_type_id,
            'state': 'draft',
            'origin': _("Exchange of %s") % self.picking_id.name,
            'location_id': self.picking_id.location_dest_id.id,
            'location_dest_id': self.location_id.id}
        return vals

    def create_new_picking(self):
        # created exchange picking form the active picking based on the
        # parameters entered
        # get product_exchange_moves which needed action
        # - have move_id and non zero quantity
        need_action_moves = self.product_exchange_moves.filtered(
            lambda m: m.move_id and not float_is_zero(
                m.quantity,
                precision_rounding=m.product_id.uom_id.rounding))

        if not need_action_moves:
            # then no picking have to be created
            return

        # create new picking for returned products
        picking_type_id = self.picking_id.picking_type_id.return_picking_type_id.id or self.picking_id.picking_type_id.id
        new_picking_values = self._prepare_new_picking_values(picking_type_id)

        new_picking = self.picking_id.copy(new_picking_values)

        # post a message in the new exchange picking defining the origin
        new_picking.message_post_with_view('mail.message_origin_link',
                                           values={'self': new_picking, 'origin': self.picking_id},
                                           subtype_id=self.env.ref('mail.mt_note').id)

        for exchange_line in need_action_moves:
            vals = self._prepare_move_default_values(exchange_line, new_picking)

            # delete not done or canceled dest moves
            exchange_line.move_id.move_dest_ids.filtered(
                lambda m: m.state not in ('done', 'cancel'))._do_unreserve()

            # swap exchange_line.move_id dest_ids and orig_ids in the new created move (the exchange_line.move_id added as orig_ids)
            move_orig_to_link = exchange_line.move_id.move_dest_ids.mapped('returned_move_ids')
            move_dest_to_link = exchange_line.move_id.move_orig_ids.mapped('returned_move_ids')
            vals['move_orig_ids'] = [(4, m.id)
                                     for m in move_orig_to_link | exchange_line.move_id]
            vals['move_dest_ids'] = [(4, m.id) for m in move_dest_to_link]

            exchange_line.move_id.copy(vals)

        new_picking.action_confirm()
        new_picking.action_assign()

        # add the created exchange pickings to active picking exchange_pickings_ids
        self.picking_id.exchange_pickings_ids = [(4, new_picking.id)]
        return

    def _prepare_invoice_line_values(self, move):
        # the data for the new inovice line
        vals = {
            'name': move.product_id.name,
            'product_id': move.product_id.id,
            'price_unit': move.price_unit,
            'quantity': move.quantity,
            'uom_id': move.uom_id and move.uom_id.id or move.move_id.product_uom and move.move_id.product_uom.id or False,
        }
        return vals

    def create_invoices(self):
        # get product_exchange_moves which needed action
        # - don't have purchase_line_id or sale_line_id and non zero quantity
        # - have purchase_line_id or sale_line_id and non zero quantity and price != to original price
        # if the new price is greator than the price in sale or purchase order new customer invoice will be created
        # if the new price is less than the price in sale or purchase order new refund invoice will be created
        # if a new product is added a new customer invoice will be created

        # get moves of the new added products to product_exchange_moves
        need_action_moves = self.product_exchange_moves.filtered(
            lambda
            m: (not m.purchase_line_id and not m.sale_line_id)
            and not float_is_zero(m.quantity, precision_rounding=m.product_id.uom_id.rounding))

        # get moves of the products related to purchase order in product_exchange_moves
        need_action_moves_purchase = self.product_exchange_moves.filtered(
            lambda m: m.purchase_line_id
            and
            not
            float_is_zero(m.quantity, precision_rounding=m.product_id.uom_id.rounding)
            and m.price_unit != m.purchase_line_id.price_unit)

        # get moves of the products related to sale order in product_exchange_moves
        need_action_moves_sale = self.product_exchange_moves.filtered(
            lambda m: m.sale_line_id
            and
            not float_is_zero(m.quantity, precision_rounding=m.product_id.uom_id.rounding)
            and m.price_unit != m.sale_line_id.price_unit)

        new_cusotmer_invoices = {}
        new_purchase_refund_invoices = {}
        new_sale_refund_invoices = {}

        # for the newly added products
        if need_action_moves:
            new_cusotmer_invoices[self.partner_id.id] = {
                'partner_id': self.partner_id.id,
                'invoice_line_ids': [],
                'date_invoice': fields.Date.context_today(self),
            }
            line_ids = []
            for move in need_action_moves:
                line_ids.append(
                    (0, 0,
                     self._prepare_invoice_line_values(move)))
            new_cusotmer_invoices[self.partner_id.id]['invoice_line_ids'] = line_ids

        # prepare new customer invoices and vendor refunds from purchase order related move
        for move in need_action_moves_purchase:
            new_line = self._prepare_invoice_line_values(move)
            new_line['purchase_line_id'] = move.purchase_line_id.id
            new_line = (0, 0, new_line)
            partner_id = move.purchase_line_id.partner_id.id
            if move.price_unit > move.purchase_line_id.price_unit:
                new_cusotmer_invoices[partner_id] = new_cusotmer_invoices.get(
                    partner_id,
                    {'partner_id': partner_id, 'invoice_line_ids': [],
                     'date_invoice': fields.Date.context_today(self),
                     'purchase_id': move.purchase_line_id.order_id.id,
                     'origin': _("Exchange of %s") % self.picking_id.name, })
                new_cusotmer_invoices[partner_id]['invoice_line_ids'].append(
                    new_line)
            elif move.price_unit < move.purchase_line_id.price_unit:
                new_purchase_refund_invoices[partner_id] = new_purchase_refund_invoices.get(
                    partner_id,
                    {'partner_id': partner_id, 'invoice_line_ids': [],
                     'date_invoice': fields.Date.context_today(self),
                     'purchase_id': move.purchase_line_id.order_id.id,
                     'origin': _("Exchange of %s") % self.picking_id.name, })
                new_purchase_refund_invoices[partner_id]['invoice_line_ids'].append(
                    new_line)

        # prepare new customer invoices and customer refunds from sale order related move
        for move in need_action_moves_sale:
            new_line = self._prepare_invoice_line_values(move)
            new_line['sale_line_ids'] = [(4, move.sale_line_id.id)]
            new_line = (0, 0, new_line)

            partner_id = move.sale_line_id.order_partner_id.id
            if move.price_unit > move.sale_line_id.price_unit:
                new_cusotmer_invoices[partner_id] = new_cusotmer_invoices.get(
                    partner_id, {'partner_id': partner_id, 'invoice_line_ids': [],
                                 'date_invoice': fields.Date.context_today(self),
                                 'origin': _("Exchange of %s") % self.picking_id.name, })
                new_cusotmer_invoices[partner_id]['invoice_line_ids'].append(
                    new_line)
            elif move.price_unit < move.sale_line_id.price_unit:
                new_sale_refund_invoices[partner_id] = new_sale_refund_invoices.get(
                    partner_id, {'partner_id': partner_id, 'invoice_line_ids': [],
                                 'date_invoice': fields.Date.context_today(self),
                                 'origin': _("Exchange of %s") % self.picking_id.name, })
                new_sale_refund_invoices[partner_id]['invoice_line_ids'].append(
                    new_line)

        new_invoices = []

        # create customer invoices
        for key in new_cusotmer_invoices:
            invoice_line_ids = new_cusotmer_invoices[key]['invoice_line_ids']
            new_cusotmer_invoices[key]['invoice_line_ids'] = []

            new_id = self.env['account.invoice'].with_context(
                type='out_invoice', journal_type='sale').create(
                new_cusotmer_invoices[key])

            new_id.with_context(type=new_id.type, journal_id=new_id.journal_id.id,
                                default_invoice_id=new_id.id).write({
                                    'invoice_line_ids': invoice_line_ids})
            new_invoices.append(new_id.id)

        # create vendor refund invoices
        for key in new_purchase_refund_invoices:
            invoice_line_ids = new_purchase_refund_invoices[key]['invoice_line_ids']
            new_purchase_refund_invoices[key]['invoice_line_ids'] = []

            new_id = self.env['account.invoice'].with_context(
                default_type='in_refund', type='in_refund', journal_type='purchase').create(
                new_purchase_refund_invoices[key])

            new_id.with_context(type=new_id.type, journal_id=new_id.journal_id.id,
                                default_invoice_id=new_id.id).write({
                                    'invoice_line_ids': invoice_line_ids})
            new_invoices.append(new_id.id)

        # create customer refund invoices
        for key in new_sale_refund_invoices:
            invoice_line_ids = new_sale_refund_invoices[key]['invoice_line_ids']
            new_sale_refund_invoices[key]['invoice_line_ids'] = []

            new_id = self.env['account.invoice'].with_context(
                default_type='out_refund', type='out_refund', journal_type='sale').create(
                new_sale_refund_invoices[key])

            new_id.with_context(type=new_id.type, journal_id=new_id.journal_id.id,
                                default_invoice_id=new_id.id).write({
                                    'invoice_line_ids': invoice_line_ids})
            new_invoices.append(new_id.id)

        # add new invoices to the exchange_invoices_ids in the active picking_id
        if new_invoices:
            self.picking_id.exchange_invoices_ids = [(4, x) for x in new_invoices]

    def exchange_products(self):
        for wizard in self:
            wizard.create_new_picking()
            wizard.create_invoices()
