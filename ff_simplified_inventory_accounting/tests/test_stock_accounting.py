# -*- coding: utf-8 -*-

from .common import FFTestCommon


class TestStockAccounting(FFTestCommon):
    """Verify the module only configures Odoo and that Odoo's native engine
    produces the expected accounting entries (no duplicate engine)."""

    def setUp(self):
        super(TestStockAccounting, self).setUp()
        self._enable_feature()
        # Anglo-Saxon accounting so COGS is recognized at customer invoice
        # validation (Test 7).
        self.company.anglo_saxon_accounting = True
        self.category = self.env['product.category'].create({'name': 'Stock Test Cat'})
        self.product = self._create_product(self.category, cost=100.0)

    def _line_balance(self, move, account):
        """Sum of balances of a move's lines on the given account (abs)."""
        lines = move.line_ids.filtered(lambda l: l.account_id == account)
        return sum(abs(l.balance) for l in lines)

    # ---------------------------------------------------------------------
    # Test 4 — receipt: native SVL + stock journal entry, no duplicate
    # ---------------------------------------------------------------------
    def test_04_receipt_creates_native_entries(self):
        self._receive(self.product, qty=10.0)

        svl = self.env['stock.valuation.layer'].search([
            ('product_id', '=', self.product.id),
        ])
        self.assertEqual(len(svl), 1, 'One valuation layer expected for one receipt')

        moves = self._stock_journal_moves()
        self.assertEqual(len(moves), 1, 'Exactly one stock journal entry expected (no duplicate)')
        move = moves[0]
        # Valuation account debited with the value (10 * 100).
        self.assertEqual(self._line_balance(move, self.stock_valuation_account), 1000.0,
                         'Stock Valuation account must be used')
        self.assertEqual(self._line_balance(move, self.stock_input_account), 1000.0,
                         'Stock Interim Received account must be used as counterpart')

    # ---------------------------------------------------------------------
    # Test 5 — vendor bill settles the interim received account
    # ---------------------------------------------------------------------
    def test_05_vendor_bill_settles_interim_account(self):
        self._receive(self.product, qty=5.0)
        bill = self._create_vendor_bill(self.product, qty=5.0, price=100.0)

        self.assertEqual(bill.state, 'posted')
        # The bill line must hit the interim received account (native flow).
        bill_input = sum(abs(l.balance) for l in bill.line_ids
                         if l.account_id == self.stock_input_account)
        self.assertEqual(bill_input, 500.0,
                         'Vendor bill must use the Stock Interim Received account')
        # Receipt credited 500, bill debited 500 -> interim account nets to 0.
        interim_balance = sum(
            l.balance for l in
            (self._stock_journal_moves() | bill).line_ids
            if l.account_id == self.stock_input_account
        )
        self.assertAlmostEqual(interim_balance, 0.0,
                               'Interim received account should be fully settled')

    # ---------------------------------------------------------------------
    # Test 6 — sale & delivery: native stock output entry, no duplicate
    # ---------------------------------------------------------------------
    def test_06_delivery_uses_native_accounts(self):
        self._receive(self.product, qty=10.0)
        self.assertEqual(self.product.qty_available, 10.0)

        self._deliver(self.product, qty=4.0)

        self.assertEqual(self.product.qty_available, 6.0, 'Quantity should decrease')
        moves = self._stock_journal_moves()
        self.assertEqual(len(moves), 2, 'Two stock journal entries expected (receipt + delivery)')
        delivery = moves[1]
        self.assertEqual(self._line_balance(delivery, self.stock_output_account), 400.0,
                         'Stock Interim Delivered account must be used')
        self.assertEqual(self._line_balance(delivery, self.stock_valuation_account), 400.0,
                         'Stock Valuation account must be credited')

    # ---------------------------------------------------------------------
    # Test 7 — customer invoice: correct Sales + COGS, no duplicate COGS
    # ---------------------------------------------------------------------
    def test_07_customer_invoice_sales_and_cogs(self):
        self._receive(self.product, qty=10.0)
        self._deliver(self.product, qty=4.0)

        invoice = self._create_customer_invoice(self.product, qty=4.0, price=150.0)
        self.assertEqual(invoice.state, 'posted')

        # Revenue on the Sales account (4 * 150).
        sales = sum(abs(l.balance) for l in invoice.line_ids
                    if l.account_id == self.income_account)
        self.assertEqual(sales, 600.0, 'Sales account must be used on the invoice')
        # COGS on the COGS account (4 * 100 cost), exactly one COGS line.
        cogs_lines = invoice.line_ids.filtered(lambda l: l.account_id == self.cogs_account)
        self.assertEqual(len(cogs_lines), 1, 'Exactly one COGS line expected (no duplicate)')
        self.assertEqual(abs(cogs_lines.balance), 400.0, 'COGS must equal delivered cost')
        # The interim delivered account is cleared by the anglo-saxon entry.
        interim = sum(
            l.balance for l in (self._stock_journal_moves() | invoice).line_ids
            if l.account_id == self.stock_output_account
        )
        self.assertAlmostEqual(interim, 0.0,
                               'Interim delivered account should be settled by COGS entry')

    # ---------------------------------------------------------------------
    # Test 8 — sales return reverses valuation
    # ---------------------------------------------------------------------
    def test_08_sales_return_reverses_valuation(self):
        self._receive(self.product, qty=10.0)
        self._deliver(self.product, qty=4.0)
        value_after_delivery = self.product.value_svl

        # Return 2 units from the customer.
        move = self.env['stock.move'].create({
            'name': self.product.name,
            'product_id': self.product.id,
            'product_uom_qty': 2.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.env.ref('stock.stock_location_customers').id,
            'location_dest_id': self.env.ref('stock.stock_location_stock').id,
        })
        move._action_confirm()
        move.quantity = 2.0
        move.picked = True
        move._action_done()

        self.assertEqual(self.product.qty_available, 8.0, 'Returned quantity restored')
        # Value restored by 2 * 100 = 200.
        self.assertAlmostEqual(self.product.value_svl, value_after_delivery + 200.0,
                               places=2, msg='Valuation should reverse on return')
        # No duplicate moves: receipt + delivery + return.
        self.assertEqual(len(self._stock_journal_moves()), 3)

    # ---------------------------------------------------------------------
    # Test 9 — purchase return reverses valuation
    # ---------------------------------------------------------------------
    def test_09_purchase_return_reverses_valuation(self):
        self._receive(self.product, qty=5.0)
        value_after_receipt = self.product.value_svl

        # Return 2 units to the supplier.
        move = self.env['stock.move'].create({
            'name': self.product.name,
            'product_id': self.product.id,
            'product_uom_qty': 2.0,
            'product_uom': self.product.uom_id.id,
            'location_id': self.env.ref('stock.stock_location_stock').id,
            'location_dest_id': self.env.ref('stock.stock_location_suppliers').id,
        })
        move._action_confirm()
        move.quantity = 2.0
        move.picked = True
        move._action_done()

        self.assertEqual(self.product.qty_available, 3.0, 'Returned quantity reduced')
        self.assertAlmostEqual(self.product.value_svl, value_after_receipt - 200.0,
                               places=2, msg='Valuation should reverse on purchase return')
        self.assertEqual(len(self._stock_journal_moves()), 2,
                         'Receipt + return = 2 entries, no duplicate')
