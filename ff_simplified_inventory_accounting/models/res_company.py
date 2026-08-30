# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

# Same restriction as the standard income/expense category accounts in Odoo 18
# (see addons/account/models/product.py -> ACCOUNT_DOMAIN).
FF_ACCOUNT_DOMAIN = [
    ('deprecated', '=', False),
    ('account_type', 'not in', [
        'asset_receivable',
        'liability_payable',
        'asset_cash',
        'liability_credit_card',
        'off_balance',
    ]),
]


class ResCompany(models.Model):
    _inherit = 'res.company'

    ff_simplified_inventory_accounting = fields.Boolean(
        string='Simplified Inventory Accounting',
        help='Automatically configure inventory accounting for product '
             'categories. Users only need to select Sales and Cost of Goods '
             'Sold accounts on each category.',
    )

    # ---- User defaults ----------------------------------------------------
    ff_default_income_account_id = fields.Many2one(
        'account.account',
        string='Default Sales Account',
        domain=FF_ACCOUNT_DOMAIN,
        help='Revenue from products in categories using the simplified '
             'inventory accounting will use this account by default unless '
             'overridden on the category or product.',
    )
    ff_default_cogs_account_id = fields.Many2one(
        'account.account',
        string='Default Cost of Goods Sold Account',
        domain=FF_ACCOUNT_DOMAIN,
        help='Expense / COGS for products in categories using the simplified '
             'inventory accounting will use this account by default unless '
             'overridden on the category or product.',
    )
    ff_default_cost_method = fields.Selection(
        [('standard', 'Standard Price'),
         ('fifo', 'First In First Out (FIFO)'),
         ('average', 'Average Cost (AVCO)')],
        string='Default Costing Method',
        default='average',
        help='Default costing method applied to newly created product '
             'categories when simplified inventory accounting is enabled.',
    )

    # ---- Technical inventory accounting (advanced) ------------------------
    ff_stock_valuation_account_id = fields.Many2one(
        'account.account',
        string='Stock Valuation Account',
        domain=FF_ACCOUNT_DOMAIN,
        help='When automated inventory valuation is enabled, this account '
             'holds the current value of the products.',
    )
    ff_stock_input_account_id = fields.Many2one(
        'account.account',
        string='Stock Interim Received Account',
        domain=FF_ACCOUNT_DOMAIN,
        help='Counterpart journal items for all incoming stock moves are '
             'posted in this account.',
    )
    ff_stock_output_account_id = fields.Many2one(
        'account.account',
        string='Stock Interim Delivered Account',
        domain=FF_ACCOUNT_DOMAIN,
        help='Counterpart journal items for all outgoing stock moves are '
             'posted in this account.',
    )
    ff_stock_journal_id = fields.Many2one(
        'account.journal',
        string='Stock Journal',
        help='When doing automated inventory valuation, this is the '
             'accounting journal in which entries are automatically posted '
             'when stock moves are processed.',
    )

    # -------------------------------------------------------------------------
    # Helpers reused by product.category create/write/auto-heal and by the
    # repair wizard.
    # -------------------------------------------------------------------------
    @api.constrains(
        'ff_simplified_inventory_accounting',
        'ff_default_income_account_id',
        'ff_default_cogs_account_id',
        'ff_stock_valuation_account_id',
        'ff_stock_input_account_id',
        'ff_stock_output_account_id',
        'ff_stock_journal_id',
    )
    def _check_ff_simplified_complete(self):
        """Never allow a partially configured (enabled) feature.

        Fires on any change of the configuration fields so an enabled feature
        cannot silently become incomplete afterwards.
        """
        for company in self:
            if not company.ff_simplified_inventory_accounting:
                continue
            missing = company._ff_missing_technical_vals()
            if missing:
                labels = {
                    'ff_default_income_account_id': _('Default Sales Account'),
                    'ff_default_cogs_account_id': _('Default Cost of Goods Sold Account'),
                    'ff_stock_valuation_account_id': _('Stock Valuation Account'),
                    'ff_stock_input_account_id': _('Stock Interim Received Account'),
                    'ff_stock_output_account_id': _('Stock Interim Delivered Account'),
                    'ff_stock_journal_id': _('Stock Journal'),
                }
                raise ValidationError(
                    _('Simplified Inventory Accounting cannot be enabled because '
                      'the following required values are missing: %(fields)s.',
                      fields=', '.join(labels.get(n, n) for n in missing))
                )

    @api.model
    def _ff_required_technical_names(self):
        """Field names that must be configured for simplified accounting."""
        return [
            'ff_stock_valuation_account_id',
            'ff_stock_input_account_id',
            'ff_stock_output_account_id',
            'ff_stock_journal_id',
        ]

    def _ff_missing_technical_vals(self):
        """Return the list of missing technical configuration field names.

        Only meaningful when the feature is enabled.
        """
        self.ensure_one()
        if not self.ff_simplified_inventory_accounting:
            return []
        missing = []
        for fname in self._ff_required_technical_names():
            if not self[fname]:
                missing.append(fname)
        # User defaults are also required (sales + cogs), otherwise new
        # categories would silently end up incomplete.
        if not self.ff_default_income_account_id:
            missing.append('ff_default_income_account_id')
        if not self.ff_default_cogs_account_id:
            missing.append('ff_default_cogs_account_id')
        return missing

    def _ff_is_valid(self):
        """True when the company has a fully valid simplified configuration."""
        self.ensure_one()
        return self.ff_simplified_inventory_accounting and not self._ff_missing_technical_vals()

    def _ff_technical_vals(self):
        """Mapping of product.category stock properties -> company values.

        Returns only the properties actually configured at company level so
        callers never overwrite an existing value with an empty one.
        """
        self.ensure_one()
        vals = {}
        if self.ff_stock_valuation_account_id:
            vals['property_stock_valuation_account_id'] = self.ff_stock_valuation_account_id.id
        if self.ff_stock_input_account_id:
            vals['property_stock_account_input_categ_id'] = self.ff_stock_input_account_id.id
        if self.ff_stock_output_account_id:
            vals['property_stock_account_output_categ_id'] = self.ff_stock_output_account_id.id
        if self.ff_stock_journal_id:
            vals['property_stock_journal'] = self.ff_stock_journal_id.id
        return vals

    def _ff_category_default_vals(self, explicit_income=None, explicit_expense=None):
        """Full set of defaults to apply on a new category for this company.

        ``explicit_income`` / ``explicit_expense`` (records or ids) are
        preserved when provided; otherwise the company defaults are used.
        """
        self.ensure_one()
        income_id = explicit_income.id if hasattr(explicit_income, 'id') else explicit_income
        expense_id = explicit_expense.id if hasattr(explicit_expense, 'id') else explicit_expense
        vals = {}
        if income_id:
            vals['property_account_income_categ_id'] = income_id
        elif self.ff_default_income_account_id:
            vals['property_account_income_categ_id'] = self.ff_default_income_account_id.id
        if expense_id:
            vals['property_account_expense_categ_id'] = expense_id
        elif self.ff_default_cogs_account_id:
            vals['property_account_expense_categ_id'] = self.ff_default_cogs_account_id.id
        if self.ff_default_cost_method:
            vals['property_cost_method'] = self.ff_default_cost_method
        vals.update(self._ff_technical_vals())
        return vals

    # -------------------------------------------------------------------------
    # Automatic setup (used by the post-install hook and the settings button).
    # -------------------------------------------------------------------------
    def _ff_next_free_account_code(self, base=100000):
        """Generate a collision-safe numeric account code for the company."""
        codes = self.env['account.account'].search([
            ('company_ids', 'in', self.ids),
        ]).mapped('code')
        numeric = [int(c) for c in codes if c.isdigit()]
        next_code = (max(numeric) + 1) if numeric else base
        while str(next_code) in codes:
            next_code += 1
        return str(next_code)

    def _ff_next_free_journal_code(self):
        codes = self.env['account.journal'].search([
            ('company_id', '=', self.id),
        ]).mapped('code')
        base = 'STK'
        candidate = base
        suffix = 1
        while candidate in codes:
            suffix += 1
            candidate = '%s%03d' % (base, suffix)
        return candidate

    def _ff_ensure_technical_accounts(self):
        """Create the missing technical inventory accounts + stock journal.

        - Never overwrites existing accounts / journals.
        - Generates collision-safe codes.
        - Uses the correct account types (asset_current).
        - Stock interim (input / output) accounts are created reconcilable
          (like Odoo's native interim accounts) because the POS / invoice
          flows settle them by reconciliation.
        - Creates company-specific records, clearly identified.

        Returns the records created (empty when nothing was needed).
        """
        self.ensure_one()
        created = []
        Account = self.env['account.account']

        def create_account(fname, name, reconcile=False):
            existing = self[fname]
            if existing:
                return existing
            account = Account.with_company(self).create({
                'code': self._ff_next_free_account_code(),
                'name': '[FF Simplified] %s' % name,
                'account_type': 'asset_current',
                'company_ids': [(6, 0, self.ids)],
                'reconcile': reconcile,
                'deprecated': False,
            })
            created.append(account)
            self[fname] = account.id
            return account

        create_account('ff_stock_valuation_account_id', 'Stock Valuation', reconcile=False)
        create_account('ff_stock_input_account_id', 'Stock Interim Received', reconcile=True)
        create_account('ff_stock_output_account_id', 'Stock Interim Delivered', reconcile=True)

        if not self.ff_stock_journal_id:
            journal = self.env['account.journal'].with_company(self).create({
                'name': '[FF Simplified] Stock Valuation',
                'code': self._ff_next_free_journal_code(),
                'type': 'general',
                'company_id': self.id,
            })
            self.ff_stock_journal_id = journal.id
            created.append(journal)
        return created

    def _ff_category_ids_without_stored(self, fname):
        """IDs of categories with no *stored* company_dependent value for
        ``fname`` (they only rely on an ``ir.default`` / generic fallback).

        The ORM does not expose whether a company_dependent value is stored
        per-company or inherited from ``ir.default``, so the automatic setup
        uses the JSONB column directly to align legacy categories to the
        company defaults without touching deliberate per-category choices.

        ``fname`` must belong to a small whitelist of category properties.
        """
        allowed = {
            'property_cost_method',
            'property_valuation',
            'property_account_income_categ_id',
            'property_account_expense_categ_id',
        }
        if fname not in allowed:
            return []
        self.env.cr.execute(
            'SELECT id FROM product_category '
            'WHERE NOT (COALESCE(%s, \'{}\'::jsonb) ? %%s)' % fname,
            (str(self.id),),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _ff_auto_setup(self):
        """Full automatic configuration (used right after installation).

        - Fills Sales / COGS defaults from the standard chart when empty.
        - Creates the technical inventory accounts + the stock journal.
        - Applies the full configuration to every existing product category
          (valuation = automated, costing method, technical accounts and
          Sales / COGS), filling only missing values and never overwriting an
          explicit per-category choice.
        - Enables the feature only when the configuration is complete.

        Idempotent: running it again only fills values still missing.
        """
        self.ensure_one()
        company = self.with_company(self)
        if not self.env['account.account'].search_count([]):
            # No chart of accounts yet: nothing safe to configure.
            return

        # 1) Sales / COGS defaults from the standard chart when empty.
        #    A real chart has many income and expense accounts, so the lookup
        #    is prioritised:
        #      - Sales default: the standard income (revenue) account type,
        #        then any income-group account.
        #      - COGS default: the "Cost of Goods Sold" account type
        #        (expense_direct_cost) first, then the general expense type,
        #        then any expense-group account.
        IrDefault = self.env['ir.default']
        Account = self.env['account.account']
        chart_domain = [
            ('deprecated', '=', False),
            ('company_ids', 'in', company.id),
        ]
        if not company.ff_default_income_account_id:
            income = IrDefault._get(
                'product.category', 'property_account_income_categ_id',
                company_id=company.id)
            if not income:
                income = Account.search(
                    [('account_type', '=', 'income')] + chart_domain, limit=1)
            if not income:
                income = Account.search(
                    [('internal_group', '=', 'income')] + chart_domain, limit=1)
            if income:
                company.ff_default_income_account_id = income
        if not company.ff_default_cogs_account_id:
            cogs = IrDefault._get(
                'product.category', 'property_account_expense_categ_id',
                company_id=company.id)
            if not cogs:
                cogs = Account.search(
                    [('account_type', '=', 'expense_direct_cost')] + chart_domain,
                    limit=1)
            if not cogs:
                cogs = Account.search(
                    [('account_type', '=', 'expense')] + chart_domain, limit=1)
            if not cogs:
                cogs = Account.search(
                    [('internal_group', '=', 'expense')] + chart_domain, limit=1)
            if cogs:
                company.ff_default_cogs_account_id = cogs

        # 2) Technical inventory accounts + stock journal.
        company._ff_ensure_technical_accounts()

        # 3) Enable the feature only when the configuration is complete.
        required = (company._ff_required_technical_names()
                    + ['ff_default_income_account_id', 'ff_default_cogs_account_id'])
        if any(not company[fname] for fname in required):
            return
        if not company.ff_simplified_inventory_accounting:
            company.ff_simplified_inventory_accounting = True

        # 4) Apply to every existing product category.
        #    - Valuation is forced to Automated (this is the module's purpose:
        #      pre-existing categories left on Manual are the bug being fixed).
        #    - Technical accounts + journal are aligned to the company config.
        #    - Costing method: only categories without a *stored* choice (they
        #      rely on the generic Odoo fallback) are aligned to the company
        #      default; deliberate per-category choices are preserved.
        #    - Sales/COGS are only filled when missing: explicit per-category
        #      choices (including the native hierarchy) are always preserved —
        #      those are the only manual inputs.
        no_stored_cost = set(self._ff_category_ids_without_stored('property_cost_method'))
        for category in self.env['product.category'].search([]):
            category_c = category.with_company(company)
            vals = {}
            if category_c.property_valuation != 'real_time':
                vals['property_valuation'] = 'real_time'
            if category.id in no_stored_cost and company.ff_default_cost_method:
                vals['property_cost_method'] = company.ff_default_cost_method
            if (not category_c.property_account_income_categ_id
                    and not category_c._ff_ancestor_has('property_account_income_categ_id')
                    and company.ff_default_income_account_id):
                vals['property_account_income_categ_id'] = company.ff_default_income_account_id.id
            if (not category_c.property_account_expense_categ_id
                    and not category_c._ff_ancestor_has('property_account_expense_categ_id')
                    and company.ff_default_cogs_account_id):
                vals['property_account_expense_categ_id'] = company.ff_default_cogs_account_id.id
            vals.update({
                'property_stock_account_input_categ_id': company.ff_stock_input_account_id.id,
                'property_stock_account_output_categ_id': company.ff_stock_output_account_id.id,
                'property_stock_valuation_account_id': company.ff_stock_valuation_account_id.id,
                'property_stock_journal': company.ff_stock_journal_id.id,
            })
            category_c.write(vals)
