odoo.define('delivery_exchange.related_pro', function (require) {
    "use strict";

    var core = require('web.core');
    var rpc = require('web.rpc');
    var registry = require('web.field_registry');

    var FieldChar = require('web.basic_fields').FieldChar;

    var relatedProcesses = FieldChar.extend({

        events: {
            'click .open_picking': '_open_picking',
            'click .open_invoice': '_open_invoice',

        },

        _render: function () {

            var self = this;

            var call_data = {
                model: 'stock.picking',
                method: "get_related_processes",
                args: [this.res_id],
            }

            rpc.query(call_data)
                .then(function (result) {
                    if (result['exchange_pickings_ids'] != undefined) {
                        self.exchange_pickings_ids = result['exchange_pickings_ids'];
                        self.exchange_pickings_ids_len = self.exchange_pickings_ids.length;
                    }
                    if (result['exchange_invoices_ids'] != undefined) {
                        self.exchange_invoices_ids = result['exchange_invoices_ids'];
                        self.exchange_invoices_ids_len = self.exchange_invoices_ids.length;
                    }

                    var $el = $(core.qweb.render('delivery_exchange.processesList', {
                        widget: self
                    }).trim());
                    self._replaceElement($el);


                    var acc = document.getElementsByClassName("custom_accordion");

                    var i;

                    for (i = 0; i < acc.length; i++) {
                        acc[i].addEventListener("click", function () {
                            this.classList.toggle("active");
                            var panel = this.nextElementSibling;
                            if (panel.style.maxHeight) {
                                panel.style.maxHeight = null;
                            } else {
                                panel.style.maxHeight = panel.scrollHeight + "px";
                            }
                        });
                    }


                });


        },


        _open_picking: function (event) {
            try {
                var rec_id = parseInt($(event.currentTarget).data('rec-id'));
                event.stopPropagation();
                event.preventDefault();


                this.do_action({
                    type: 'ir.actions.act_window',
                    res_model: 'stock.picking',
                    res_id: rec_id,
                    views: [
                        [false, 'form']
                    ],
                    target: 'current',
                }, {
                    on_reverse_breadcrumb: this.on_reverse_breadcrumb,
                });

            } catch (error) {

            }

        },

        _open_invoice: function (event) {
            // get appropriate view for invoice depend on it's type
            var self = this;
            try {
                var rec_id = parseInt($(event.currentTarget).data('rec-id'));
                var type = $(event.currentTarget).data('rec-type');

                event.stopPropagation();
                event.preventDefault();


                var view_id = false;
                var view_name = 'invoice_form';
                if(type  == 'in_invoice' || type == 'in_refund'){
                    view_name = 'invoice_supplier_form'
                }
                
                var call_data = {
                    model: 'ir.model.data',
                    method: "get_object_reference",
                    args: ['account', view_name],
                }


                rpc.query(call_data).then(function (result) {
                    view_id = result[1];

                    self.do_action({
                        type: 'ir.actions.act_window',
                        res_model: 'account.invoice',
                        res_id: rec_id,
                        views: [
                            [view_id, 'form']
                        ],
                        target: 'current',
                    }, {
                        on_reverse_breadcrumb: self.on_reverse_breadcrumb,
                    });

                });




            } catch (error) {

            }

        },




    });

    registry.add('related_processes', relatedProcesses);

    return {
        relatedProcesses: relatedProcesses,
    };

});