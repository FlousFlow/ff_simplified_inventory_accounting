# -*- coding: utf-8 -*-
{
    'name': 'Simplified Inventory Accounting',
    'version': '18.0.1.6.0',
    'category': 'Inventory',
    'summary': 'Simplify Odoo 18 product category accounting: choose Sales and COGS accounts, everything else is configured automatically',
    'description': """
Simplified Inventory Accounting
===============================

Makes product category accounting configuration as simple as in Odoo 19,
while keeping Odoo 18's native stock_account engine untouched.

The user only needs to choose on each product category:

* Sales (Revenue) Account
* Cost of Goods Sold (COGS) Account
* Costing Method (optional)

All technical inventory accounting properties (stock valuation account,
stock input / interim received account, stock output / interim delivered
account and the stock journal) are configured automatically from the
company-level technical configuration.

Key benefits
------------

* simpler product category configuration;
* automatic technical stock accounting;
* prevents missing inventory accounts;
* supports existing and new categories;
* centralized per-company configuration;
* preserves standard Odoo accounting engine;
* multi-company support;
* no duplicate accounting engine.

The module only configures Odoo. Odoo creates the accounting entries.
""",
    'author': 'Flous Flow',
    'website': 'https://flousflow.com',
    'license': 'LGPL-3',
    'images': [
        'static/description/thumbnail.png',
        'static/description/banner.png',
        'static/description/cover.png',
        'static/description/icon.png',
    ],
    'depends': [
        'account',
        'stock',
        'stock_account',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_category_views.xml',
        'views/inventory_accounting_health_views.xml',
        'wizard/accounting_repair_wizard_views.xml',
        'wizard/accounting_migration_wizard_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
