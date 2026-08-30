# -*- coding: utf-8 -*-

from .common import FFTestCommon


class TestExtendedFlows(FFTestCommon):
    """Extended accounting flows: interim-account reconciliation (the POS
    settlement path), inventory adjustments, partial billing and the
    idempotency of the automatic setup."""

    def setUp(self):
        super(TestExtendedFlows, self).setUp()
        self._enable_feature()
        self.company.anglo_saxon_accounting = True
        self.category = self.env['product.category'].create({'name': 'Extended Cat'})
        self.product = self._create_product(self.category, cost=100.0)

    def _adjustment_location(self):
        """The 'Inventory adjustment' location (usage=inventory)."""
        return self.env['stock.location'].search([
            ('name', '=', 'Inventory adjustment'),
            ('usage', '=', 'inventory'),
        ], limit=1)

    # ---------------------------------------------------------------------
    # Interim-account reconciliation (the POS / invoice settlement path)
    # ---------------------------------------------------------------------
    def test_30_interim_accounts_can_be_reconciled(self):
        """The Interim Delivered account must allow reconciliation so the POS
        / invoice flows can settle it (regression test for the POS close bug)."""
        self._receive(self.product, qty=10.0)      # Dr Valuation / Cr Interim Rec
        self._deliver(self.product, qty=4.0)       # Dr Interim Delivered / Cr Valuation
        invoice = self._create_customer_invoice(self.product, qty=4.0, price=150.0)

        # The interim delivered account holds the paired debit (delivery) and
        # credit (invoice COGS entry).
        lines = self.env['account.move.line'].search([
            ('account_id', '=', self.stock_output_account.id),
            ('parent_state', '=', 'posted'),
        ])
        self.assertTrue(lines, 'Interim Delivered lines must exist')
        self.assertEqual(len(lines), 2, 'One debit (delivery) + one credit (invoice)')

        # Reconciliation must succeed (account allows it).
        lines.reconcile()
        self.assertTrue(
            all(line.full_reconcile_id for line in lines),
            'Interim Delivered lines must be fully reconciled'
        )
        # No residual balance remains on the interim account.
        residual = sum(line.balance for line in lines)
        self.assertAlmostEqual(residual, 0.0, places=2,
                               msg='Interim Delivered must net to zero after reconciliation')

    # ---------------------------------------------------------------------
    # Inventory adjustment (فروق مخزنية) uses the configured accounts
    # ---------------------------------------------------------------------
    def test_31_inventory_adjustment_uses_configured_accounts(self):
        self._receive(self.product, qty=10.0)
        adj_loc = self._adjustment_location()
        self.assertTrue(adj_loc, 'Test needs the Inventory adjustment location')
        # A surplus discovered by a count: 2 units come back into stock.
        move = self._create_move(
            self.product, adj_loc,
            self.env.ref('stock.stock_location_stock'), qty=2.0,
        )
        move._action_confirm()
        move.quantity = 2.0
        move.picked = True
        move._action_done()

        moves = self._stock_journal_moves()
        self.assertEqual(len(moves), 2, 'Receipt + adjustment = two stock entries')
        adjustment = moves[-1]
        # 2 extra units @ 100 -> valuation +200, using the configured accounts.
        self.assertEqual(self._line_balance(adjustment, self.stock_valuation_account), 200.0)
        self.assertEqual(self._line_balance(adjustment, self.stock_input_account), 200.0)

    # ---------------------------------------------------------------------
    # Partial billing leaves the remaining interim received open
    # ---------------------------------------------------------------------
    def test_32_partial_bill_leaves_interim_balance(self):
        self._receive(self.product, qty=10.0)      # interim received credited 1000
        bill = self._create_vendor_bill(self.product, qty=4.0, price=100.0)  # debits 400
        interim_bal = sum(
            l.balance
            for l in (self._stock_journal_moves() | bill).line_ids
            if l.account_id == self.stock_input_account
        )
        self.assertAlmostEqual(abs(interim_bal), 600.0, places=2,
                               msg='Partial billing leaves 6 units worth of interim received open')

    # ---------------------------------------------------------------------
    # Automatic setup is idempotent
    # ---------------------------------------------------------------------
    def test_33_auto_setup_is_idempotent(self):
        company = self.env['res.company'].create({
            'name': 'FF Idempotent Co', 'currency_id': self.currency.id,
        })
        income = self._create_account(company, 'FFIDM1', 'I Sales', 'income')
        cogs = self._create_account(company, 'FFIDM2', 'I COGS', 'expense_direct_cost')
        company.write({
            'ff_default_income_account_id': income.id,
            'ff_default_cogs_account_id': cogs.id,
            'ff_simplified_inventory_accounting': False,
        })
        category = self.env['product.category'].with_company(company).create({
            'name': 'Idempotent Cat', 'parent_id': False,
        })

        company.with_company(company)._ff_auto_setup()
        first_valuation = company.ff_stock_valuation_account_id
        first_input = company.ff_stock_input_account_id
        first_output = company.ff_stock_output_account_id
        first_journal = company.ff_stock_journal_id

        # Second run must not create new accounts / journals or change config.
        company.with_company(company)._ff_auto_setup()
        self.assertEqual(company.ff_stock_valuation_account_id, first_valuation)
        self.assertEqual(company.ff_stock_input_account_id, first_input)
        self.assertEqual(company.ff_stock_output_account_id, first_output)
        self.assertEqual(company.ff_stock_journal_id, first_journal)
        self.assertTrue(company.ff_simplified_inventory_accounting)

        cat_view = category.with_company(company)
        self.assertEqual(cat_view.property_valuation, 'real_time')
        self.assertEqual(cat_view.property_stock_journal, first_journal)
        self.assertEqual(cat_view.property_stock_account_input_categ_id, first_input)
