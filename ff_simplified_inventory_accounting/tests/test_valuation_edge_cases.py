# -*- coding: utf-8 -*-

"""Edge cases around valuation automation (regression coverage).

These complement the main suites by locking down the behavior at the seams:
- The Odoo 18 core default (``manual_periodic``) must never leak through and
  disable automation while the feature is enabled.
- With the feature disabled, the module must stay completely out of the way and
  respect explicit user choices.
- The write auto-heal, the category hierarchy and the accounting status are
  deterministic.
"""

from .common import FFTestCommon


class TestValuationEdgeCases(FFTestCommon):
    """Deterministic behavior at the valuation/automation seams."""

    def setUp(self):
        super(TestValuationEdgeCases, self).setUp()
        self._enable_feature()

    # ---------------------------------------------------------------------
    # default_get must expose automated defaults when the feature is enabled
    # ---------------------------------------------------------------------
    def test_default_get_forced_automated_when_enabled(self):
        defaults = self.env['product.category'].default_get(
            ['property_valuation', 'property_cost_method'])
        self.assertEqual(defaults.get('property_valuation'), 'real_time',
                         'Valuation default must be automated when enabled')
        self.assertEqual(defaults.get('property_cost_method'), 'average',
                         'Cost method default must come from the company')

    # ---------------------------------------------------------------------
    # default_get must keep Odoo's native manual default when disabled
    # ---------------------------------------------------------------------
    def test_default_get_keeps_native_when_disabled(self):
        self.company.ff_simplified_inventory_accounting = False
        defaults = self.env['product.category'].default_get(
            ['property_valuation'])
        # Odoo 18's core ir.default for the valuation is manual_periodic.
        self.assertEqual(defaults.get('property_valuation'), 'manual_periodic')

    # ---------------------------------------------------------------------
    # Feature disabled: a manual choice must be respected (no forcing)
    # ---------------------------------------------------------------------
    def test_disabled_feature_respects_manual_valuation(self):
        self.company.ff_simplified_inventory_accounting = False
        category = self.env['product.category'].create({
            'name': 'Manual Category',
            'property_valuation': 'manual_periodic',
        })
        category = category.with_company(self.company)
        self.assertEqual(category.property_valuation, 'manual_periodic',
                         'With the feature disabled the module must not force automation')

    # ---------------------------------------------------------------------
    # Feature disabled: an explicit automated choice must also be honored
    # ---------------------------------------------------------------------
    def test_disabled_feature_respects_explicit_automated(self):
        self.company.ff_simplified_inventory_accounting = False
        category = self.env['product.category'].create({
            'name': 'Explicit Automated',
            'property_valuation': 'real_time',
        })
        category = category.with_company(self.company)
        self.assertEqual(category.property_valuation, 'real_time')

    # ---------------------------------------------------------------------
    # write auto-heal: flipping valuation to real_time fills missing technical
    # properties (it must not overwrite existing values)
    # ---------------------------------------------------------------------
    def test_write_autoheal_fills_technical_accounts(self):
        self.company.ff_simplified_inventory_accounting = False
        category = self.env['product.category'].create({
            'name': 'Heal On Write',
            'property_valuation': 'manual_periodic',
        })
        category = category.with_company(self.company)
        self.assertEqual(category.property_valuation, 'manual_periodic')
        # Clear the native technical properties so the auto-heal has something
        # to fill (feature still disabled -> no auto-heal on this write).
        category.write({
            'property_stock_valuation_account_id': False,
            'property_stock_account_input_categ_id': False,
            'property_stock_account_output_categ_id': False,
            'property_stock_journal': False,
        })

        self._enable_feature()
        category.write({'property_valuation': 'real_time'})
        category = category.with_company(self.company)
        self.assertEqual(category.property_stock_valuation_account_id,
                         self.stock_valuation_account,
                         'Auto-heal must fill the stock valuation account')
        self.assertEqual(category.property_stock_account_input_categ_id,
                         self.stock_input_account)
        self.assertEqual(category.property_stock_account_output_categ_id,
                         self.stock_output_account)
        self.assertEqual(category.property_stock_journal, self.stock_journal)

    # ---------------------------------------------------------------------
    # Category hierarchy: a child inherits the ancestor's accounts and must
    # not be blindly overwritten with the company defaults
    # ---------------------------------------------------------------------
    def test_child_inherits_ancestor_accounts(self):
        parent = self.env['product.category'].create({
            'name': 'Parent Node',
            'property_account_income_categ_id': self.income_account.id,
            'property_account_expense_categ_id': self.cogs_account.id,
        })
        child = self.env['product.category'].create({
            'name': 'Child Node',
            'parent_id': parent.id,
        })
        child = child.with_company(self.company)
        self.assertEqual(child.property_account_income_categ_id, self.income_account)
        self.assertEqual(child.property_account_expense_categ_id, self.cogs_account)
        self.assertEqual(child.property_valuation, 'real_time')

    # ---------------------------------------------------------------------
    # Accounting status: configured / custom / warning are deterministic
    # ---------------------------------------------------------------------
    def test_accounting_status_configured(self):
        category = self.env['product.category'].create({'name': 'Status OK'})
        category = category.with_company(self.company)
        self.assertEqual(category.ff_accounting_status, 'configured',
                         'A fully defaulted category must be "configured"')

    def test_accounting_status_custom_income(self):
        custom_income = self._create_account(self.company, 'FFCUST', 'Custom Sales', 'income')
        category = self.env['product.category'].create({
            'name': 'Status Custom',
            'property_account_income_categ_id': custom_income.id,
        })
        category = category.with_company(self.company)
        self.assertEqual(category.ff_accounting_status, 'custom',
                         'A category with a non-default income account must be "custom"')

    def test_accounting_status_warning_when_incomplete(self):
        self.company.ff_simplified_inventory_accounting = False
        category = self.env['product.category'].create({
            'name': 'Status Warning',
            'property_valuation': 'real_time',
        })
        category = category.with_company(self.company)
        # Make it genuinely incomplete: no income/expense accounts (feature
        # disabled -> no auto-heal, so the clear persists).
        category.write({
            'property_account_income_categ_id': False,
            'property_account_expense_categ_id': False,
        })
        self.assertEqual(category.ff_accounting_status, 'warning',
                         'A category missing income/expense must be "warning"')
