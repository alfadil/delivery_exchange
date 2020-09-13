# -*- coding: utf-8 -*-
{
    'name': "Delivery Exchange",

    'summary': """
        Add Delivery Exchange feature to stock""",

    'description': """
        Delivery Exchange allow you to Exchange products after the transfer completded.\n
        - allow the user to add products to the exchange product which were not the the original picking.\n
        - automaticly create invoice when the price of exchanged product not equals to the original prices in the sale or purchase order.\n

    """,

    'author': "Alfadil",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/12.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Warehouse',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['purchase_stock','sale_stock','sale_management'],

    # always loaded
    'data': [
        'wizard/stock_delivery_exchange_views.xml',
        'views/stock_picking_views.xml',
        'views/views.xml',
    ],

    'qweb': ["static/src/xml/template.xml"],

    
}
