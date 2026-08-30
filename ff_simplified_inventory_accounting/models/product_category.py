# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.osv import expression


class ProductCategory(models.Model):
    _inherit = 'product.category'

    ff_accounting_status = fields.Selection(
        [('configured', 'Configured'),
         ('custom', 'Custom'),
         ('warning', 'Warning')],
        compute='_compute_ff_accounting_status',
        search='_search_ff_accounting_status',
        string='Accounting Status',
    )
    # Contextual helper used by the views to switch between the simplified
    # form (feature enabled for the current company) and the standard form.
    ff_simplified_enabled = fields.Boolean(
        compute='_compute_ff_simplified_enabled',
        string='Simplified Inventory Accounting Enabled',
    )

    def _compute_ff_simplified_enabled(self):
        enabled = self.env.company.ff_simplified_inventory_accounting
        for category in self:
            category.ff_simplified_enabled = enabled

    @api.model
    def default_get(self, fields_list):
        """Ensure the simplified-mode helper field is available when creating
        a new category (the web client reads defaults, not computed values,
        for new records), and default the costing method to the company's
        choice so a new category does not silently keep Odoo's generic default.
        """
        res = super(ProductCategory, self).default_get(fields_list)
        if 'ff_simplified_enabled' in fields_list:
            res['ff_simplified_enabled'] = self.env.company.ff_simplified_inventory_accounting
        company = self.env.company
        if (company.ff_simplified_inventory_accounting
                and company.ff_default_cost_method
                and 'property_cost_method' in fields_list):
            # Override Odoo's generic ir.default so the form shows the
            # company's choice (create() applies it anyway; this only fixes
            # what the user sees before saving).
            res['property_cost_method'] = company.ff_default_cost_method
        if (company.ff_simplified_inventory_accounting
                and 'property_valuation' in fields_list):
            # Odoo 18's generic default for the valuation is "manual_periodic".
            # The web client loads that default into the (hidden) form field and
            # sends it back on save, which would silently disable automation.
            # Force the default to "real_time" so the form never starts manual.
            res['property_valuation'] = 'real_time'
        return res

    @api.model
    def _search_ff_accounting_status(self, operator, value):
        """Translate a status filter into a domain on the underlying fields.

        The status is a computed, non-stored field, so searching / grouping on
        it requires a custom search method.
        """
        if operator not in ('=', '!=', 'in', 'not in'):
            return [('id', 'in', [])]
        company = self.env.company

        real_time = ('property_valuation', '=', 'real_time')
        technical_fields = [
            'property_stock_account_input_categ_id',
            'property_stock_account_output_categ_id',
            'property_stock_valuation_account_id',
            'property_stock_journal',
        ]
        warning_terms = []
        for f in technical_fields:
            warning_terms += ['&', real_time, (f, '=', False)]
        warning_domain = ['|'] * 5 + warning_terms + [
            ('property_account_income_categ_id', '=', False),
            ('property_account_expense_categ_id', '=', False),
        ]

        def complete_technical():
            dom = [real_time]
            for f in technical_fields:
                dom.append((f, '!=', False))
            return dom

        default_income = company.ff_default_income_account_id
        default_cogs = company.ff_default_cogs_account_id
        base_valid = complete_technical() + [
            ('property_account_income_categ_id', '!=', False),
            ('property_account_expense_categ_id', '!=', False),
        ]

        if operator == '!=':
            # Not(status) is only meaningfully inverted for '='.
            domain = [('id', 'in', [])]
        elif value == 'warning':
            domain = warning_domain
        elif value == 'configured':
            if default_income and default_cogs:
                domain = base_valid + [
                    ('property_account_income_categ_id', '=', default_income.id),
                    ('property_account_expense_categ_id', '=', default_cogs.id),
                ]
            else:
                # Without company defaults nothing can be "configured".
                domain = [('id', 'in', [])]
        elif value == 'custom':
            if default_income or default_cogs:
                custom_income = ('property_account_income_categ_id', '!=', default_income.id or False)
                custom_cogs = ('property_account_expense_categ_id', '!=', default_cogs.id or False)
                domain = ['|'] + base_valid + [custom_income, custom_cogs]
            else:
                # Without company defaults any complete category is "custom".
                domain = base_valid
        else:
            domain = [('id', 'in', [])]

        if operator in ('not in',) or (operator == '!='):
            # Invert the resulting domain (approximation for != / not in).
            negated = expression.AND([domain])
            return [('id', 'not in', self.search(negated).ids)]
        return domain

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------
    @api.depends('property_valuation', 'property_cost_method',
                 'property_stock_account_input_categ_id',
                 'property_stock_account_output_categ_id',
                 'property_stock_valuation_account_id',
                 'property_stock_journal',
                 'property_account_income_categ_id',
                 'property_account_expense_categ_id')
    def _compute_ff_accounting_status(self):
        company = self.env.company
        for category in self:
            missing = []
            if category.property_valuation == 'real_time':
                for fname in ('property_stock_account_input_categ_id',
                              'property_stock_account_output_categ_id',
                              'property_stock_valuation_account_id'):
                    if not category[fname]:
                        missing.append(fname)
                if not category.property_stock_journal:
                    missing.append('property_stock_journal')
            if not category.property_account_income_categ_id:
                missing.append('property_account_income_categ_id')
            if not category.property_account_expense_categ_id:
                missing.append('property_account_expense_categ_id')

            if missing:
                category.ff_accounting_status = 'warning'
            elif (company.ff_default_income_account_id
                    and category.property_account_income_categ_id == company.ff_default_income_account_id
                    and company.ff_default_cogs_account_id
                    and category.property_account_expense_categ_id == company.ff_default_cogs_account_id):
                category.ff_accounting_status = 'configured'
            else:
                category.ff_accounting_status = 'custom'

    # -------------------------------------------------------------------------
    # Create: apply company defaults when the feature is enabled.
    # -------------------------------------------------------------------------
    def _ff_ancestor_has(self, fname):
        """True when an ancestor category already provides a value for the
        company-dependent field ``fname`` under the current company.

        Preserves Odoo's native category hierarchy for income/expense accounts.
        """
        parent = self.parent_id
        while parent:
            if parent.with_company(self.env.company)[fname]:
                return True
            parent = parent.parent_id
        return False

    @api.model_create_multi
    def create(self, vals_list):
        company = self.env.company
        new_vals_list = []
        for vals in vals_list:
            if company.ff_simplified_inventory_accounting:
                new_vals = self._ff_prepare_create_vals(vals, company)
                new_vals_list.append(new_vals)
            else:
                new_vals_list.append(vals)
        return super(ProductCategory, self).create(new_vals_list)

    def _ff_prepare_create_vals(self, vals, company):
        """Build the create values for a new category under ``company``.

        - Sales / COGS: preserve explicit user choice, otherwise use the
          company default, unless an ancestor already provides a value (native
          category hierarchy is preserved).
        - Valuation: real_time unless the user explicitly chose otherwise.
        - Costing method: preserve explicit choice, otherwise company default.
        - Technical stock accounts: always from company configuration.
        """
        vals = dict(vals)
        explicit_income = vals.get('property_account_income_categ_id')
        explicit_expense = vals.get('property_account_expense_categ_id')

        # Native hierarchy first: if an ancestor has an account, let the child
        # inherit instead of forcing the company default.
        if not explicit_income and not self._ff_ancestor_has('property_account_income_categ_id'):
            explicit_income = explicit_income or company.ff_default_income_account_id.id or False
        if not explicit_expense and not self._ff_ancestor_has('property_account_expense_categ_id'):
            explicit_expense = explicit_expense or company.ff_default_cogs_account_id.id or False

        defaults = company._ff_category_default_vals(
            explicit_income=explicit_income,
            explicit_expense=explicit_expense,
        )

        # Merge: company defaults first, then explicit user values win.
        merged = dict(defaults)
        merged.update({k: v for k, v in vals.items() if v})

        # Valuation is always automated for new categories while the feature is
        # enabled. Odoo 18's core default for property_valuation is
        # "manual_periodic", which the web client sends back from the (hidden)
        # form field; treating it as an explicit user choice would silently
        # disable automation. Force "real_time" unconditionally here — this
        # method is only called when the feature is enabled for the company.
        merged['property_valuation'] = 'real_time'
        return merged

    # -------------------------------------------------------------------------
    # Write: auto-heal technical properties when the feature is enabled.
    # -------------------------------------------------------------------------
    def _ff_compute_autoheal_vals(self, company, valuation=None):
        """Return category property values to restore from company config.

        Only fills *missing* technical properties for real-time valuation.
        ``valuation`` may be provided to account for a valuation change in the
        same write.
        """
        vals = {}
        if valuation is None:
            valuation = self.property_valuation
        if valuation != 'real_time':
            return vals
        mapping = {
            'property_stock_account_input_categ_id': company.ff_stock_input_account_id,
            'property_stock_account_output_categ_id': company.ff_stock_output_account_id,
            'property_stock_valuation_account_id': company.ff_stock_valuation_account_id,
            'property_stock_journal': company.ff_stock_journal_id,
        }
        for fname, account in mapping.items():
            if account and not self[fname]:
                vals[fname] = account.id
        return vals

    def write(self, vals):
        if not self._context.get('ff_skip_accounting_sync'):
            company = self.env.company
            if company.ff_simplified_inventory_accounting:
                for category in self:
                    category_c = category.with_company(company)
                    new_valuation = vals.get(
                        'property_valuation', category_c.property_valuation)
                    for fname, value in category_c._ff_compute_autoheal_vals(
                            company, valuation=new_valuation).items():
                        if fname in vals and not vals[fname]:
                            # Explicit deliberate clearing in advanced mode.
                            continue
                        vals.setdefault(fname, value)
        return super(ProductCategory, self).write(vals)
