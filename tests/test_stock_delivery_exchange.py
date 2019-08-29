# -*- coding: utf-8 -*-
from odoo.tests import common
from odoo.addons.stock.tests.common import TestStockCommon
from datetime import datetime

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

from odoo import api, registry
from odoo.tests import tagged


@tagged('standard', 'del_exch')
class stockDeliveryExchangeTest(TestStockCommon):
    def create_pick_ship(self):
        picking_client = self.env['stock.picking'].create({
            'location_id': self.pack_location,
            'location_dest_id': self.customer_location,
            'partner_id': self.partner_delta_id,
            'picking_type_id': self.picking_type_out,
        })

        dest = self.MoveObj.create({
            'name': self.productA.name,
            'product_id': self.productA.id,
            'product_uom_qty': 10,
            'product_uom': self.productA.uom_id.id,
            'picking_id': picking_client.id,
            'location_id': self.pack_location,
            'location_dest_id': self.customer_location,
            'state': 'waiting',
            'procure_method': 'make_to_order',
        })

        picking_pick = self.env['stock.picking'].create({
            'location_id': self.stock_location,
            'location_dest_id': self.pack_location,
            'partner_id': self.partner_delta_id,
            'picking_type_id': self.picking_type_out,
        })

        self.MoveObj.create({
            'name': self.productA.name,
            'product_id': self.productA.id,
            'product_uom_qty': 10,
            'product_uom': self.productA.uom_id.id,
            'picking_id': picking_pick.id,
            'location_id': self.stock_location,
            'location_dest_id': self.pack_location,
            'move_dest_ids': [(4, dest.id)],
            'state': 'confirmed',
        })
        return picking_pick, picking_client

    def test_picking_exchange(self):
        # test the exchange process without being linked to sale or purchase order
        picking_pick, picking_client = self.create_pick_ship()
        stock_location = self.env['stock.location'].browse(self.stock_location)
        self.env['stock.quant']._update_available_quantity(self.productA, stock_location, 44.0)

        picking_pick.action_assign()
        picking_pick.move_lines[0].move_line_ids[0].qty_done = 44.0
        picking_pick.action_done()
        self.assertEqual(picking_pick.state, 'done')
        self.assertEqual(picking_client.state, 'assigned')

        # exchange a part of what we've done
        stock_delivery_exchange = self.env['stock.delivery.exchange']\
            .with_context(active_ids=picking_pick.ids, active_id=picking_pick.ids[0])\
            .create({})
        stock_delivery_exchange.product_exchange_moves.quantity = 33
        stock_delivery_exchange.exchange_products()

        self.assertEqual(len(picking_pick.exchange_pickings_ids), 1)

        exchange_pick = picking_pick.exchange_pickings_ids[0]

        exchange_pick.move_lines.move_line_ids.qty_done = 33
        exchange_pick.action_done()
        # check the exchange picking is in done state
        self.assertEqual(exchange_pick.state, 'done')


@tagged('standard', 'del_exch')
class stockDeliveryExchangeTestSale(common.TransactionCase):
    def setUp(self):
        super(stockDeliveryExchangeTestSale, self).setUp()

        self.partner = self.env.ref('base.res_partner_1')
        self.first_product = self.env.ref('product.product_delivery_01')
        self.second_product = self.env.ref('product.product_delivery_02')
        self.third_product = self.env.ref('product.product_order_01')
        self.fourth_product = self.env.ref('product.product_product_3')


    def test_picking_exchange_sale(self):
        """
            Test a SO with a product invoiced on delivery. Deliver and invoice the SO, then do a exchange
            of the picking. Check that a refund and customer invoices well be generated.
            """

        # intial so
        
        so_vals = {
            'partner_id': self.partner.id,
            'partner_invoice_id': self.partner.id,
            'partner_shipping_id': self.partner.id,
            'order_line': [(0, 0, {
                'name': self.first_product.name,
                'product_id': self.first_product.id,
                'product_uom_qty': 5.0,
                'product_uom': self.first_product.uom_id.id,
                'price_unit': 30.0}),
                (0, 0, {
                    'name': self.second_product.name,
                    'product_id': self.second_product.id,
                    'product_uom_qty': 5.0,
                    'product_uom': self.second_product.uom_id.id,
                    'price_unit': 40.0}),
                (0, 0, {
                    'name': self.third_product.name,
                    'product_id': self.third_product.id,
                    'product_uom_qty': 5.0,
                    'product_uom': self.third_product.uom_id.id,
                    'price_unit': 50.0})],
            'pricelist_id': self.env.ref('product.list0').id,
        }
        self.so = self.env['sale.order'].create(so_vals)

        # confirm our standard so, check the picking
        self.so.action_confirm()
        self.assertTrue(
            self.so.picking_ids,
            'Delivery Exchange: no picking created for "invoice on delivery" storable products')

        # deliver completely
        pick = self.so.picking_ids
        pick.move_lines.write({'quantity_done': 5})
        pick.button_validate()

        # Check quantity delivered
        del_qty = sum(sol.qty_delivered for sol in self.so.order_line)
        self.assertEqual(
            del_qty, 15.0,
            'Delivery Exchange: delivered quantity should be 15.0 instead of %s after complete delivery' %
            del_qty)

        # Create exchange picking
        stock_delivery_exchange_obj = self.env['stock.delivery.exchange']
        default_data = stock_delivery_exchange_obj.with_context(
            active_ids=pick.ids, active_id=pick.ids[0]).default_get(
            ['move_dest_exists', 'original_location_id', 'product_exchange_moves',
             'parent_location_id', 'location_id'])
        exchange_wiz = stock_delivery_exchange_obj.with_context(
            active_ids=pick.ids, active_id=pick.ids[0]).create(default_data)

        exchange_wiz.partner_id = self.partner.id
        exchange_wiz.product_exchange_moves.write({'quantity':2.0, 'price_unit': 40.0})

        exchange_wiz.product_exchange_moves = [(0, 0, {
            'name': self.fourth_product.name,
            'product_id': self.fourth_product.id,
            'quantity': 5.0,
            'product_uom': self.fourth_product.uom_id.id,
            'price_unit': 30.0})]
        exchange_wiz.exchange_products()
        exchange_pick = pick.exchange_pickings_ids[0]

        # Validate picking
        exchange_pick.move_lines.write({'quantity_done': 2})
        exchange_pick.action_done()

        self.assertEqual(exchange_pick.state, 'done')

        out_refund_inv = pick.exchange_invoices_ids.filtered(lambda inv: inv.type == 'out_refund')
        self.assertEqual(
            len(out_refund_inv), 1.0,
            msg='there must be one refund invoices ')

        out_refund_inv_qty = sum(line.quantity for line in out_refund_inv[0].invoice_line_ids)
        self.assertEqual(
            out_refund_inv_qty, 2.0,
            msg='Delivery Exchange: in refund invoice quantity should be 2.0 instead of "%s" after picking exchange' %
            out_refund_inv_qty)

        out_invoice_inv = pick.exchange_invoices_ids.filtered(lambda inv: inv.type == 'out_invoice')
        self.assertEqual(
            len(out_invoice_inv), 1.0,
            msg='there must be one customer invoices ')

        out_invoice_inv_qty = sum(line.quantity for line in out_invoice_inv[0].invoice_line_ids)
        self.assertEqual(
            out_invoice_inv_qty, 7.0,
            msg='Delivery Exchange: in customer invoice quantity should be 7.0 instead of "%s" after picking exchange' %
            out_invoice_inv_qty)

        del_qty = sum(sol.qty_delivered for sol in self.so.order_line)

        self.assertEqual(
            del_qty, 9.0,
            msg='Delivery Exchange: delivered quantity should be 9.0 instead of "%s" after picking exchange' %
            del_qty)


@tagged('standard', 'del_exch')
class stockDeliveryExchangeTestPurchase(common.TransactionCase):

    def setUp(self):
        super(stockDeliveryExchangeTestPurchase, self).setUp()

        self.partner_id = self.env.ref('base.res_partner_1')
        self.partner_id_2 = self.env.ref('base.res_partner_2')
        self.first_product = self.env.ref('product.product_delivery_01')
        self.second_product = self.env.ref('product.product_delivery_02')
        self.third_product = self.env.ref('product.product_order_01')
        self.fourth_product = self.env.ref('product.product_product_3')

    def test_picking_exchange_purchase(self):
        """
        Test a PO with a product on Incoming shipment. Validate the PO, then do a exchange
        of the picking with Refund to .check customer and refund invoices will be generated
        """
        self.partner_id = self.env.ref('base.res_partner_1')
        self.first_product = self.env.ref('product.product_product_8')
        self.second_product = self.env.ref('product.product_product_11')
        self.third_product = self.env.ref('product.product_order_01')
        self.fourth_product = self.env.ref('product.product_product_3')

        # Draft purchase order created
        self.po_vals = {
            'partner_id': self.partner_id.id,
            'order_line': [
                (0, 0, {
                    'name': self.first_product.name,
                    'product_id': self.first_product.id,
                    'product_qty': 50.0,
                    'product_uom': self.first_product.uom_po_id.id,
                    'price_unit': 500.0,
                    'date_planned': datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                }),
                (0, 0, {
                    'name': self.second_product.name,
                    'product_id': self.second_product.id,
                    'product_qty': 50.0,
                    'product_uom': self.second_product.uom_po_id.id,
                    'price_unit': 250.0,
                    'date_planned': datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                }),
                (0, 0, {
                    'name': self.third_product.name,
                    'product_id': self.third_product.id,
                    'product_qty': 50.0,
                    'product_uom': self.third_product.uom_po_id.id,
                    'price_unit': 200.0,
                    'date_planned': datetime.today().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                })],
        }

        self.po = self.env['purchase.order'].create(self.po_vals)
        self.assertTrue(self.po, 'Delivery Exchange: no purchase order created')
        self.assertEqual(self.po.order_line.mapped('qty_received'), [
                         0.0, 0.0, 0.0], 'Delivery Exchange: no product should be received"')
        self.assertEqual(self.po.order_line.mapped('qty_invoiced'), [
                         0.0, 0.0, 0.0], 'Delivery Exchange: no product should be invoiced"')

        # Confirm the purchase order
        self.po.button_confirm()
        self.assertEqual(self.po.state, 'purchase',
                         'Delivery Exchange: PO state should be "Purchase')

        # Check created picking
        self.assertEqual(self.po.picking_count, 1,
                         'Delivery Exchange: one picking should be created"')
        self.picking = self.po.picking_ids[0]
        self.picking.move_line_ids.write({'qty_done': 50.0})
        self.picking.button_validate()
        self.assertEqual(self.po.order_line.mapped('qty_received'), [
                         50.0, 50.0, 50.0], 'Delivery Exchange: all products should be received"')

        # Check quantity received
        received_qty = sum(pol.qty_received for pol in self.po.order_line)
        self.assertEqual(
            received_qty, 150.0,
            'Delivery Exchange: Received quantity should be 150.0 instead of %s after validating incoming shipment'
            % received_qty)

        # Create Delivery exchange picking
        stock_delivery_exchange_obj = self.env['stock.delivery.exchange']
        pick = self.po.picking_ids
        default_data = stock_delivery_exchange_obj.with_context(
            active_ids=pick.ids, active_id=pick.ids[0]).default_get(
            ['move_dest_exists', 'original_location_id', 'product_exchange_moves',
             'parent_location_id', 'location_id'])
        exchange_wiz = stock_delivery_exchange_obj.with_context(
            active_ids=pick.ids, active_id=pick.ids[0]).create(default_data)
        
        exchange_wiz.partner_id = self.partner_id_2.id

        exchange_wiz.product_exchange_moves.write({'quantity': 10.0, 'price_unit': 250.0})
        
        exchange_wiz.product_exchange_moves = [(0, 0, {
            'name': self.fourth_product.name,
            'product_id': self.fourth_product.id,
            'quantity': 5.0,
            'product_uom': self.fourth_product.uom_id.id,
            'price_unit': 30.0})]
            
        exchange_wiz.exchange_products()
        exchange_pick = pick.exchange_pickings_ids[0]

        # Validate picking
        exchange_pick.move_line_ids.write({'qty_done': 10})
        exchange_pick.action_done()

        self.assertEqual(exchange_pick.state, 'done')



        in_refund_inv = pick.exchange_invoices_ids.filtered(lambda inv: inv.type == 'in_refund')
        self.assertEqual(
            len(in_refund_inv), 1.0,
            msg='there must be one refund invoices ')

        in_refund_inv_qty = sum(line.quantity for line in in_refund_inv[0].invoice_line_ids)
        self.assertEqual(
            in_refund_inv_qty, 10.0,
            msg='Delivery Exchange: in refund invoice quantity should be 10.0 instead of "%s" after picking exchange' %
            in_refund_inv_qty)

        out_invoice_inv = pick.exchange_invoices_ids.filtered(lambda inv: inv.type == 'out_invoice')
        self.assertEqual(
            len(out_invoice_inv), 2.0,
            msg='there must be two customer invoices ')
        
        out_invoice_inv_qty = 0.0
        for inv in out_invoice_inv:
            for line in inv.invoice_line_ids:
                out_invoice_inv_qty += line.quantity

        self.assertEqual(
            out_invoice_inv_qty, 15.0,
            msg='Delivery Exchange: in customer invoice quantity should be 15.0 instead of "%s" after picking exchange' %
            out_invoice_inv_qty)

        # Check quantity received
        received_qty = sum(pol.qty_received for pol in self.po.order_line)
        self.assertEqual(
            received_qty, 120.0,
            'Delivery Exchange: delivered quantity should be 120.0 instead of "%s" after delivery exchange' %
            received_qty)
        

