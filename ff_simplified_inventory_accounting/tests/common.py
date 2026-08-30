# -*- coding: utf-8 -*-

from odoo import fields
from odoo.tests.common import TransactionCase


class FFTestCommon(TransactionCase):
    """Shared setup: company configuration, accounts, journals, helpers.

    All tests run against the standard Odoo 18 accounting engine. The module
    under test only configures Odoo; the tests verify that Odoo then produces
    the expected accounting behavior with no duplicate engine.
    """

    @classmethod
    def setUpClass(cls):
        super(FFTestCommon, cls).setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        # --- Generic accounts / journal used by the company config ----------
        cls.income_account = cls._create_account(cls.company, 'FFSAL', 'FF Sales', 'income')
        cls.cogs_account = cls._create_account(cls.company, 'FFCOGS', 'FF COGS', 'expense_direct_cost')
        cls.stock_valuation_account = cls._create_account(cls.company, 'FFVAL', 'FF Stock Valuation', 'asset_current')
        cls.stock_input_account = cls._create_account(cls.company, 'FFINP', 'FF Stock Input', 'asset_current')
        cls.stock_output_account = cls._create_account(cls.company, 'FFOUT', 'FF Stock Output', 'asset_current')
        # Like Odoo's native interim accounts, the stock input / output accounts
        # must allow reconciliation (the POS / invoice flows settle them).
        cls.stock_input_account.reconcile = True
        cls.stock_output_account.reconcile = True
        cls.stock_journal = cls._create_journal(cls.company, 'FFSTJ', 'FF Stock Journal')

    @classmethod
    def _create_account(cls, company, code, name, account_type):
        return cls.env['account.account'].create({
            'code': code,
            'name': name,
            'account_type': account_type,
            'company_ids': [(6, 0, company.ids)],
        })

    @classmethod
    def _create_journal(cls, company, code, name):
        return cls.env['account.journal'].create({
            'code': code,
            'name': name,
            'type': 'general',
            'company_id': company.id,
        })

    @classmethod
    def _enable_feature(cls, company=None, income=None, cogs=None,
                        valuation=None, input_account=None, output_account=None,
                        journal=None, cost_method='average'):
        """Enable simplified inventory accounting on a company."""
        company = company or cls.company
        company.write({
            'ff_simplified_inventory_accounting': True,
            'ff_default_income_account_id': (income or cls.income_account).id,
            'ff_default_cogs_account_id': (cogs or cls.cogs_account).id,
            'ff_default_cost_method': cost_method,
            'ff_stock_valuation_account_id': (valuation or cls.stock_valuation_account).id,
            'ff_stock_input_account_id': (input_account or cls.stock_input_account).id,
            'ff_stock_output_account_id': (output_account or cls.stock_output_account).id,
            'ff_stock_journal_id': (journal or cls.stock_journal).id,
        })
        return company

    # -------------------------------------------------------------------------
    # Stock / accounting helpers
    # -------------------------------------------------------------------------
    def _create_product(self, category, cost=100.0, name=None):
        return self.env['product.product'].create({
            'name': name or 'FF Product',
            # Odoo 18: storable goods are type 'consu' AND is_storable=True.
            'type': 'consu',
            'is_storable': True,
            'categ_id': category.id,
            'standard_price': cost,
            'sale_ok': True,
            'purchase_ok': True,
        })

    def _create_move(self, product, src, dst, qty=10.0):
        """Create a stock move exactly like Odoo 18's TestStockCommon does.

        The onchange fills company_id / uom / defaults required for the move to
        produce quants, valuation layers and the accounting entry.
        """
        Move = self.env['stock.move']
        move = Move.new({
            'product_id': product.id,
            'location_id': src.id,
            'location_dest_id': dst.id,
        })
        move._onchange_product_id()
        move_values = move._convert_to_write(move._cache)
        move_values.update({'product_uom_qty': qty})
        return Move.create(move_values)

    def _receive(self, product, qty=10.0):
        """Receive products into stock (incoming move), returning the move."""
        move = self._create_move(
            product,
            self.env.ref('stock.stock_location_suppliers'),
            self.env.ref('stock.stock_location_stock'),
            qty=qty,
        )
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def _deliver(self, product, qty=10.0):
        """Deliver products out of stock (outgoing move)."""
        move = self._create_move(
            product,
            self.env.ref('stock.stock_location_stock'),
            self.env.ref('stock.stock_location_customers'),
            qty=qty,
        )
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def _receive_lot(self, product, qty=1.0, lot_name='FFSERIAL001'):
        """Receive a lot/serial-valuated product (used by migration tests)."""
        lot = self.env['stock.lot'].create({
            'name': lot_name,
            'product_id': product.id,
            'company_id': self.company.id,
        })
        move = self._create_move(
            product,
            self.env.ref('stock.stock_location_suppliers'),
            self.env.ref('stock.stock_location_stock'),
            qty=qty,
        )
        move._action_confirm()
        move.move_line_ids.lot_id = lot.id
        move.move_line_ids.quantity = qty
        move.picked = True
        move._action_done()
        return move

    def _create_vendor_bill(self, product, qty=1.0, price=100.0):
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.env['res.partner'].create({'name': 'FF Vendor'}).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': qty,
                'price_unit': price,
            })],
        })
        bill.action_post()
        return bill

    def _create_customer_invoice(self, product, qty=1.0, price=150.0):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.env['res.partner'].create({'name': 'FF Customer'}).id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [(0, 0, {
                'product_id': product.id,
                'quantity': qty,
                'price_unit': price,
            })],
        })
        invoice.action_post()
        return invoice

    def _stock_journal_moves(self):
        """Account moves posted in the configured stock journal (oldest first)."""
        return self.env['account.move'].search([
            ('journal_id', '=', self.stock_journal.id),
            ('state', '=', 'posted'),
        ], order='id asc')

    def _account_moves_for(self, account):
        """Posted moves referencing the given account (via its lines)."""
        return self.env['account.move'].search([
            ('line_ids.account_id', '=', account.id),
            ('state', '=', 'posted'),
        ])

    def _line_balance(self, move, account):
        """Sum of absolute balances of a move's lines on the given account."""
        lines = move.line_ids.filtered(lambda l: l.account_id == account)
        return sum(abs(l.balance) for l in lines)
