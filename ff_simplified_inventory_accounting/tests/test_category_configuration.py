# -*- coding: utf-8 -*-

from odoo.exceptions import UserError, ValidationError

from .common import FFTestCommon


class TestCategoryConfiguration(FFTestCommon):
    """Product category automatic accounting configuration."""

    def setUp(self):
        super(TestCategoryConfiguration, self).setUp()
        self._enable_feature()

    # ---------------------------------------------------------------------
    # Test 1 — a new category receives all company defaults automatically
    # ---------------------------------------------------------------------
    def test_01_new_category_gets_company_defaults(self):
        category = self.env['product.category'].create({'name': 'Laptops'})
        category = category.with_company(self.company)

        self.assertEqual(category.property_account_income_categ_id, self.income_account,
                         'Sales account should default from company')
        self.assertEqual(category.property_account_expense_categ_id, self.cogs_account,
                         'COGS account should default from company')
        self.assertEqual(category.property_valuation, 'real_time',
                         'New category should default to automated valuation')
        self.assertEqual(category.property_cost_method, 'average',
                         'Costing method should default from company (AVCO)')
        self.assertEqual(category.property_stock_valuation_account_id, self.stock_valuation_account,
                         'Stock valuation account should come from company')
        self.assertEqual(category.property_stock_account_input_categ_id, self.stock_input_account,
                         'Stock input account should come from company')
        self.assertEqual(category.property_stock_account_output_categ_id, self.stock_output_account,
                         'Stock output account should come from company')
        self.assertEqual(category.property_stock_journal, self.stock_journal,
                         'Stock journal should come from company')

    # ---------------------------------------------------------------------
    # Test 2 — explicit custom Sales/COGS are preserved, technical from company
    # ---------------------------------------------------------------------
    def test_02_custom_category_accounts_are_preserved(self):
        laptop_sales = self._create_account(self.company, 'FFLSAL', 'Laptop Sales', 'income')
        laptop_cogs = self._create_account(self.company, 'FFLCOGS', 'Laptop COGS', 'expense_direct_cost')

        category = self.env['product.category'].create({
            'name': 'Laptops',
            'property_account_income_categ_id': laptop_sales.id,
            'property_account_expense_categ_id': laptop_cogs.id,
        })
        category = category.with_company(self.company)

        # Sales / COGS preserved (custom).
        self.assertEqual(category.property_account_income_categ_id, laptop_sales)
        self.assertEqual(category.property_account_expense_categ_id, laptop_cogs)
        # Technical accounts still come from the company.
        self.assertEqual(category.property_stock_valuation_account_id, self.stock_valuation_account)
        self.assertEqual(category.property_stock_account_input_categ_id, self.stock_input_account)
        self.assertEqual(category.property_stock_account_output_categ_id, self.stock_output_account)
        self.assertEqual(category.property_stock_journal, self.stock_journal)

    # ---------------------------------------------------------------------
    # Test 3 — Safe Accounting Repair syncs technical accounts + fills
    # ---------------------------------------------------------------------
    def test_03_safe_repair_syncs_company_config(self):
        # Create a 'legacy' category with the feature disabled: Odoo applies
        # its native chart defaults (different accounts from our company
        # configuration).
        self.company.ff_simplified_inventory_accounting = False
        legacy = self.env['product.category'].create({
            'name': 'Legacy Category',
            'property_valuation': 'real_time',
            'property_cost_method': 'fifo',
        })
        legacy = legacy.with_company(self.company)
        # Native defaults differ from the company's simplified configuration.
        self.assertNotEqual(legacy.property_stock_valuation_account_id,
                            self.stock_valuation_account)
        self.assertEqual(legacy.property_cost_method, 'fifo')

        # Enable the feature and run the safe repair.
        self._enable_feature()
        wizard = self.env['ff.accounting.repair.wizard'].create({})
        wizard.action_repair()

        legacy.invalidate_recordset()
        legacy = legacy.with_company(self.company)
        # Technical accounts are synced to the company configuration.
        self.assertEqual(legacy.property_stock_journal, self.stock_journal,
                         'Repair should sync the Stock Journal to company config')
        self.assertEqual(legacy.property_stock_valuation_account_id, self.stock_valuation_account,
                         'Repair should sync the Stock Valuation to company config')
        self.assertEqual(legacy.property_stock_account_input_categ_id, self.stock_input_account,
                         'Repair should sync the Stock Input to company config')
        self.assertEqual(legacy.property_stock_account_output_categ_id, self.stock_output_account,
                         'Repair should sync the Stock Output to company config')
        # Costing method must NOT be changed by safe repair.
        self.assertEqual(legacy.property_cost_method, 'fifo',
                         'Safe repair must never change the costing method')

    # ---------------------------------------------------------------------
    # Test 11 — batch / import-style ORM creation applies configuration
    # ---------------------------------------------------------------------
    def test_11_batch_creation_applies_defaults(self):
        categories = self.env['product.category'].create([
            {'name': 'Electronics'},
            {'name': 'Accessories'},
            {'name': 'Furniture'},
        ])
        self.assertEqual(len(categories), 3)
        for category in categories.with_company(self.company):
            self.assertEqual(category.property_account_income_categ_id, self.income_account)
            self.assertEqual(category.property_account_expense_categ_id, self.cogs_account)
            self.assertEqual(category.property_valuation, 'real_time')
            self.assertEqual(category.property_stock_journal, self.stock_journal)

    # ---------------------------------------------------------------------
    # Test 12 — historical category with valuation history is repaired safely
    # ---------------------------------------------------------------------
    def test_12_historical_category_repair_is_safe(self):
        self.company.ff_simplified_inventory_accounting = False
        legacy = self.env['product.category'].create({
            'name': 'Legacy Stock',
            'property_valuation': 'real_time',
            'property_stock_account_input_categ_id': self.stock_input_account.id,
            'property_stock_account_output_categ_id': self.stock_output_account.id,
            'property_stock_valuation_account_id': self.stock_valuation_account.id,
            'property_cost_method': 'fifo',
        })
        product = self._create_product(legacy, cost=100.0)
        # Give it valuation history.
        self._receive(product, qty=5.0)
        svl_before = self.env['stock.valuation.layer'].search_count([
            ('product_id', '=', product.id),
        ])
        self.assertGreater(svl_before, 0, 'Test needs existing valuation layers')

        self._enable_feature()
        wizard = self.env['ff.accounting.repair.wizard'].create({})
        wizard.action_repair()

        legacy.invalidate_recordset()
        legacy = legacy.with_company(self.company)
        # Costing / valuation untouched.
        self.assertEqual(legacy.property_cost_method, 'fifo')
        self.assertEqual(legacy.property_valuation, 'real_time')
        # Historical valuation layers untouched.
        svl_after = self.env['stock.valuation.layer'].search_count([
            ('product_id', '=', product.id),
        ])
        self.assertEqual(svl_after, svl_before,
                         'Safe repair must not touch historical valuation layers')

    # ---------------------------------------------------------------------
    # Settings validation: cannot enable a partially configured feature
    # ---------------------------------------------------------------------
    def test_13_settings_validation_blocks_incomplete_config(self):
        # Disable the feature and clear the stock valuation account so the
        # enable attempt below is genuinely incomplete.
        self.company.write({
            'ff_simplified_inventory_accounting': False,
            'ff_stock_valuation_account_id': False,
        })
        with self.assertRaises(ValidationError):
            self.env['res.config.settings'].create({
                'ff_simplified_inventory_accounting': True,
                'ff_default_income_account_id': self.income_account.id,
                'ff_default_cogs_account_id': self.cogs_account.id,
                # stock valuation account intentionally left empty
            })
        # The incomplete enable was rolled back: feature stays disabled.
        self.assertFalse(self.company.ff_simplified_inventory_accounting)

    # ---------------------------------------------------------------------
    # Migration wizard: lot/serial valuated products are blocked
    # ---------------------------------------------------------------------
    def test_14_migration_blocks_lot_valuated_products(self):
        category = self.env['product.category'].create({'name': 'Migrate Me'})
        product = self._create_product(category, cost=50.0)
        product.write({'tracking': 'serial', 'lot_valuated': True})
        self._receive_lot(product, qty=1.0)
        self.assertTrue(product.lot_valuated and product.stock_valuation_layer_ids)

        wizard = self.env['ff.accounting.migration.wizard'].create({
            'category_ids': [(6, 0, category.ids)],
            'target_cost_method': 'fifo',
        })
        with self.assertRaises(UserError):
            wizard.action_migrate()
        # Nothing changed.
        self.assertEqual(category.property_cost_method, 'average')

    # ---------------------------------------------------------------------
    # Migration wizard: safe migration uses the native mechanism
    # ---------------------------------------------------------------------
    def test_15_migration_succeeds_when_safe(self):
        category = self.env['product.category'].create({'name': 'Migrate Safe'})
        product = self._create_product(category, cost=50.0)
        self._receive(product, qty=3.0)
        svl_before = self.env['stock.valuation.layer'].search_count([
            ('product_id', '=', product.id),
        ])
        self.assertEqual(category.property_cost_method, 'average')

        wizard = self.env['ff.accounting.migration.wizard'].create({
            'category_ids': [(6, 0, category.ids)],
            'target_cost_method': 'fifo',
        })
        # Onchange is not fired on create; refresh the safety summary manually.
        wizard._onchange_refresh_safety()
        self.assertTrue(wizard.migration_safe)
        wizard.action_migrate()
        self.assertEqual(category.property_cost_method, 'fifo')
        # The native mechanism still manages the layers.
        self.assertGreaterEqual(
            self.env['stock.valuation.layer'].search_count([
                ('product_id', '=', product.id),
            ]), svl_before)

    # ---------------------------------------------------------------------
    # Test 16 — automatic setup (post-install hook) configures the whole tree
    # ---------------------------------------------------------------------
    def test_16_auto_setup_configures_whole_tree(self):
        # A company with pre-existing (unconfigured) categories where only
        # Sales / COGS are chosen: _ff_auto_setup must do everything else.
        company = self.env['res.company'].create({
            'name': 'FF Auto Setup Co',
            'currency_id': self.currency.id,
        })
        income = self._create_account(company, 'FFASAL', 'AS Sales', 'income')
        cogs = self._create_account(company, 'FFACOG', 'AS COGS', 'expense_direct_cost')
        company.write({
            'ff_default_income_account_id': income.id,
            'ff_default_cogs_account_id': cogs.id,
            'ff_simplified_inventory_accounting': False,
        })
        # Pre-existing categories (feature off -> not yet automated).
        c1 = self.env['product.category'].with_company(company).create({
            'name': 'Auto Cat 1', 'parent_id': False,
        })
        c2 = self.env['product.category'].with_company(company).create({
            'name': 'Auto Cat 2', 'parent_id': False,
        })
        self.assertNotEqual(c1.with_company(company).property_valuation, 'real_time',
                            'Pre-existing category must start unautomated')

        # Run the automatic setup (what the post-install hook does).
        company.with_company(company)._ff_auto_setup()

        # Feature enabled and technical accounts created automatically.
        self.assertTrue(company.ff_simplified_inventory_accounting)
        self.assertTrue(company.ff_stock_valuation_account_id)
        self.assertTrue(company.ff_stock_input_account_id)
        self.assertTrue(company.ff_stock_output_account_id)
        self.assertTrue(company.ff_stock_journal_id)

        # Stock interim accounts must be reconcilable (POS / invoice flows
        # settle them by reconciliation); the valuation account must not.
        self.assertFalse(company.ff_stock_valuation_account_id.reconcile,
                         'Valuation account must not be reconcilable')
        self.assertTrue(company.ff_stock_input_account_id.reconcile,
                        'Stock Interim Received must allow reconciliation')
        self.assertTrue(company.ff_stock_output_account_id.reconcile,
                        'Stock Interim Delivered must allow reconciliation')

        # Whole tree configured: automated valuation + technical accounts.
        for cat in (c1.with_company(company), c2.with_company(company)):
            self.assertEqual(cat.property_valuation, 'real_time')
            self.assertEqual(cat.property_cost_method, 'average')
            self.assertEqual(cat.property_stock_valuation_account_id,
                             company.ff_stock_valuation_account_id)
            self.assertEqual(cat.property_stock_account_input_categ_id,
                             company.ff_stock_input_account_id)
            self.assertEqual(cat.property_stock_account_output_categ_id,
                             company.ff_stock_output_account_id)
            self.assertEqual(cat.property_stock_journal, company.ff_stock_journal_id)
            self.assertEqual(cat.property_account_income_categ_id, income)
            self.assertEqual(cat.property_account_expense_categ_id, cogs)

    # ---------------------------------------------------------------------
    # Test 17 — an empty valuation sent on create must not disable automation
    # ---------------------------------------------------------------------
    def test_17_empty_valuation_still_becomes_automated(self):
        # Simulate a form / import that sends an empty valuation value.
        category = self.env['product.category'].create({
            'name': 'Auto Forced',
            'property_valuation': False,
        })
        category = category.with_company(self.company)
        self.assertEqual(category.property_valuation, 'real_time',
                         'An empty valuation on create must still be automated')
        self.assertEqual(category.property_stock_journal, self.stock_journal)

    # ---------------------------------------------------------------------
    # Test 17b — the core Odoo 18 default (manual_periodic) must not disable
    # automation on create (the actual UI bug)
    # ---------------------------------------------------------------------
    def test_17b_core_manual_default_still_becomes_automated(self):
        # The web client loads Odoo's generic valuation default
        # ("manual_periodic") and sends it back on create; this must not be
        # mistaken for an explicit user choice.
        category = self.env['product.category'].create({
            'name': 'Core Default Manual',
            'property_valuation': 'manual_periodic',
        })
        self.assertEqual(
            category.with_company(self.company).property_valuation,
            'real_time',
            'The core manual_periodic default must not disable automation',
        )
        # default_get must also expose automated as the form default.
        defaults = self.env['product.category'].default_get(
            ['property_valuation', 'property_cost_method'])
        self.assertEqual(defaults.get('property_valuation'), 'real_time')

    # ---------------------------------------------------------------------
    # Test 18 — auto setup enables the feature even without ir.default
    # ---------------------------------------------------------------------
    def test_18_auto_setup_enables_without_ir_default(self):
        # A fresh company whose chart provides no ir.default for the category
        # income / expense accounts: the setup must fall back to the chart.
        company = self.env['res.company'].create({
            'name': 'FF NoDefault Co', 'currency_id': self.currency.id,
        })
        income = self._create_account(company, 'FFND1', 'ND Sales', 'income')
        cogs = self._create_account(company, 'FFND2', 'ND COGS', 'expense_direct_cost')
        company.write({'ff_simplified_inventory_accounting': False})

        company.with_company(company)._ff_auto_setup()

        self.assertTrue(company.ff_simplified_inventory_accounting,
                        'Feature must be enabled even without ir.default')
        self.assertEqual(company.ff_default_income_account_id, income,
                         'Income default should fall back to a chart income account')
        self.assertEqual(company.ff_default_cogs_account_id, cogs,
                         'COGS default should fall back to a chart expense account')
        # A new category under this company is automated.
        category = self.env['product.category'].with_company(company).create({
            'name': 'NoDefault Cat', 'parent_id': False,
        })
        self.assertEqual(category.with_company(company).property_valuation, 'real_time')

    # ---------------------------------------------------------------------
    # Test 19 — several income / expense accounts: sensible defaults are picked
    # ---------------------------------------------------------------------
    def test_19_multiple_accounts_pick_sensible_defaults(self):
        """A chart with many income and expense accounts: the setup picks the
        standard income type for Sales and the Cost of Goods Sold account for
        COGS."""
        company = self.env['res.company'].create({
            'name': 'FF Multi Co', 'currency_id': self.currency.id,
        })
        self._create_account(company, 'FFMINT', 'Interest Income', 'income')
        self._create_account(company, 'FFMREV', 'Product Sales', 'income')
        self._create_account(company, 'FFMSVC', 'Service Revenue', 'income')
        cogs = self._create_account(company, 'FFMCOG', 'Cost of Goods Sold', 'expense_direct_cost')
        self._create_account(company, 'FFMGEN', 'General Expenses', 'expense')
        self._create_account(company, 'FFMRNT', 'Rent Expense', 'expense')
        company.write({'ff_simplified_inventory_accounting': False})

        company.with_company(company)._ff_auto_setup()

        self.assertTrue(company.ff_simplified_inventory_accounting)
        self.assertEqual(company.ff_default_income_account_id.account_type, 'income',
                         'Sales default must be an income (revenue) account')
        self.assertEqual(company.ff_default_cogs_account_id, cogs,
                         'COGS default must be the Cost of Goods Sold account')

    # ---------------------------------------------------------------------
    # Test 20 — no Cost of Goods Sold account: COGS falls back to expense
    # ---------------------------------------------------------------------
    def test_20_no_direct_cost_account_falls_back_to_expense(self):
        """A chart without a Cost of Goods Sold account still enables the
        feature: COGS falls back to a general expense account."""
        company = self.env['res.company'].create({
            'name': 'FF NoCOGS Co', 'currency_id': self.currency.id,
        })
        self._create_account(company, 'FFN1', 'Sales', 'income')
        self._create_account(company, 'FFN2', 'Rent', 'expense')
        self._create_account(company, 'FFN3', 'Utilities', 'expense')
        company.write({'ff_simplified_inventory_accounting': False})

        company.with_company(company)._ff_auto_setup()

        self.assertTrue(company.ff_simplified_inventory_accounting)
        self.assertEqual(company.ff_default_cogs_account_id.account_type, 'expense',
                         'COGS default should fall back to the general expense type')

    # ---------------------------------------------------------------------
    # Test 21 — only non-standard income types: falls back to income group
    # ---------------------------------------------------------------------
    def test_21_income_falls_back_to_income_group(self):
        """A chart with only non-standard income types (e.g. other_income)
        still enables and picks an income-group account."""
        company = self.env['res.company'].create({
            'name': 'FF OddIncome Co', 'currency_id': self.currency.id,
        })
        self._create_account(company, 'FFO1', 'FX Gains', 'income_other')
        self._create_account(company, 'FFO2', 'Cost of Goods Sold', 'expense_direct_cost')
        company.write({'ff_simplified_inventory_accounting': False})

        company.with_company(company)._ff_auto_setup()

        self.assertTrue(company.ff_simplified_inventory_accounting)
        self.assertEqual(company.ff_default_income_account_id.internal_group, 'income',
                         'Income default should fall back to the income group')

    # ---------------------------------------------------------------------
    # Test 22 — the category exposes the company stock valuation account
    # ---------------------------------------------------------------------
    def test_22_category_stock_valuation_account_from_company(self):
        """The stock valuation account shown on the category form defaults to
        the company configuration."""
        category = self.env['product.category'].create({'name': 'Stock Acct Cat'})
        category = category.with_company(self.company)
        self.assertEqual(category.property_stock_valuation_account_id,
                         self.stock_valuation_account,
                         'Category must expose the company stock valuation account')
        self.assertFalse(category.property_stock_valuation_account_id.reconcile,
                         'The stock valuation account must not be reconcilable')

    # ---------------------------------------------------------------------
    # Test 23 — a per-category stock valuation account override is preserved
    # ---------------------------------------------------------------------
    def test_23_custom_stock_valuation_account_is_preserved(self):
        """Changing the stock valuation account on a category is preserved:
        the auto-heal must not override an explicit per-category choice."""
        category = self.env['product.category'].create({'name': 'Custom Stock Acct'})
        custom = self._create_account(self.company, 'FFCSV', 'Custom Stock Val', 'asset_current')
        category = category.with_company(self.company)
        category.property_stock_valuation_account_id = custom.id

        # A later write (e.g. editing the category) must keep the custom account.
        category.write({'name': 'Custom Stock Acct 2'})
        category = category.with_company(self.company)
        self.assertEqual(category.property_stock_valuation_account_id, custom,
                         'Explicit stock valuation account must survive later writes')
