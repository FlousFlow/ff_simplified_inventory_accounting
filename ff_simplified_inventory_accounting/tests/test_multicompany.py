# -*- coding: utf-8 -*-

from .common import FFTestCommon


class TestMultiCompany(FFTestCommon):
    """Multi-company isolation (Test 10)."""

    def setUp(self):
        super(TestMultiCompany, self).setUp()
        # Company A = main company, already configured with the feature on.
        self._enable_feature()

        # Company B with completely different accounts + cost method.
        self.company_b = self.env['res.company'].create({
            'name': 'FF Company B',
            'currency_id': self.currency.id,
        })
        self.b_income = self._create_account(self.company_b, 'FFBSAL', 'B Sales', 'income')
        self.b_cogs = self._create_account(self.company_b, 'FFBCOGS', 'B COGS', 'expense_direct_cost')
        self.b_valuation = self._create_account(self.company_b, 'FFBVAL', 'B Valuation', 'asset_current')
        self.b_input = self._create_account(self.company_b, 'FFBINP', 'B Input', 'asset_current')
        self.b_output = self._create_account(self.company_b, 'FFBOUT', 'B Output', 'asset_current')
        self.b_journal = self._create_journal(self.company_b, 'FFBSTJ', 'B Stock Journal')
        self._enable_feature(
            company=self.company_b,
            income=self.b_income,
            cogs=self.b_cogs,
            valuation=self.b_valuation,
            input_account=self.b_input,
            output_account=self.b_output,
            journal=self.b_journal,
            cost_method='fifo',
        )

    def test_10_company_dependent_properties_are_isolated(self):
        # 1. Category created under company A receives A defaults.
        category = self.env['product.category'].with_company(self.company).create({
            'name': 'Shared Category',
        })
        a_view = category.with_company(self.company)
        self.assertEqual(a_view.property_account_income_categ_id, self.income_account)
        self.assertEqual(a_view.property_stock_journal, self.stock_journal)
        self.assertEqual(a_view.property_cost_method, 'average')

        # 2. No leakage: the same category is empty under company B.
        b_view = category.with_company(self.company_b)
        self.assertFalse(b_view.property_stock_journal,
                         'Company A accounts must not leak into company B')

        # 3. A category created under company B receives B defaults.
        cat_b = self.env['product.category'].with_company(self.company_b).create({
            'name': 'B Category',
        })
        b_cat_view = cat_b.with_company(self.company_b)
        self.assertEqual(b_cat_view.property_account_income_categ_id, self.b_income)
        self.assertEqual(b_cat_view.property_stock_journal, self.b_journal)
        self.assertEqual(b_cat_view.property_cost_method, 'fifo')
        self.assertNotEqual(b_cat_view.property_account_income_categ_id, self.income_account,
                            'B must not use A accounts')

        # 4. Auto-heal on write under B fills B technical properties.
        b_view.write({'property_valuation': 'real_time'})
        b_view = category.with_company(self.company_b)
        self.assertEqual(b_view.property_stock_valuation_account_id, self.b_valuation)
        self.assertEqual(b_view.property_stock_account_input_categ_id, self.b_input)
        self.assertEqual(b_view.property_stock_account_output_categ_id, self.b_output)
        self.assertEqual(b_view.property_stock_journal, self.b_journal)

        # 5. Company A values are untouched.
        a_view = category.with_company(self.company)
        self.assertEqual(a_view.property_account_income_categ_id, self.income_account)
        self.assertEqual(a_view.property_stock_journal, self.stock_journal)
        self.assertEqual(a_view.property_cost_method, 'average')
