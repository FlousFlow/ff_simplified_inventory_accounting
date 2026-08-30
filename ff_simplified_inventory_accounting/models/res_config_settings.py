# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError

from .res_company import FF_ACCOUNT_DOMAIN


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    def _check_ff_manager(self):
        """Deny sensitive initialisation / account-creation actions to users
        who are not accounting managers.

        The UI already hides these buttons behind ``account.group_account_manager``;
        this is a defense-in-depth check so the methods cannot be invoked
        directly through the ORM / RPC.
        """
        if not self.env.user.has_group('account.group_account_manager'):
            raise AccessError(
                _('Only accounting managers can perform this action.')
            )

    # ---- Feature toggle + user defaults -----------------------------------
    ff_simplified_inventory_accounting = fields.Boolean(
        related='company_id.ff_simplified_inventory_accounting',
        readonly=False,
    )
    ff_default_income_account_id = fields.Many2one(
        'account.account',
        related='company_id.ff_default_income_account_id',
        readonly=False,
        domain=FF_ACCOUNT_DOMAIN,
    )
    ff_default_cogs_account_id = fields.Many2one(
        'account.account',
        related='company_id.ff_default_cogs_account_id',
        readonly=False,
        domain=FF_ACCOUNT_DOMAIN,
    )
    ff_default_cost_method = fields.Selection(
        related='company_id.ff_default_cost_method',
        readonly=False,
    )

    # ---- Technical inventory accounting (advanced) -------------------------
    ff_stock_valuation_account_id = fields.Many2one(
        'account.account',
        related='company_id.ff_stock_valuation_account_id',
        readonly=False,
        domain=FF_ACCOUNT_DOMAIN,
    )
    ff_stock_input_account_id = fields.Many2one(
        'account.account',
        related='company_id.ff_stock_input_account_id',
        readonly=False,
        domain=FF_ACCOUNT_DOMAIN,
    )
    ff_stock_output_account_id = fields.Many2one(
        'account.account',
        related='company_id.ff_stock_output_account_id',
        readonly=False,
        domain=FF_ACCOUNT_DOMAIN,
    )
    ff_stock_journal_id = fields.Many2one(
        'account.journal',
        related='company_id.ff_stock_journal_id',
        readonly=False,
    )

    # -------------------------------------------------------------------------
    # Validation: never allow a partially configured feature.
    # -------------------------------------------------------------------------
    def set_values(self):
        super(ResConfigSettings, self).set_values()
        for company in self.company_id:
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
                missing_labels = [labels.get(name, name) for name in missing]
                raise ValidationError(
                    _('Simplified Inventory Accounting cannot be enabled because '
                      'the following required values are missing for company '
                      '%(company)s: %(fields)s.',
                      company=company.name,
                      fields=', '.join(missing_labels))
                )

    # -------------------------------------------------------------------------
    # Initialization helpers.
    # -------------------------------------------------------------------------
    def _ff_find_best_existing_category(self):
        """Return the most complete real-time category of the company to use
        as a template when initializing company defaults."""
        self.ensure_one()
        company = self.company_id
        Category = self.env['product.category']
        categories = Category.search([
            ('property_valuation', '=', 'real_time'),
        ]).with_company(company)
        # Only categories belonging to this company (company_dependent values
        # are stored per company; empty values mean not configured here).
        def completeness(cat):
            return sum(bool(cat[f]) for f in [
                'property_stock_valuation_account_id',
                'property_stock_account_input_categ_id',
                'property_stock_account_output_categ_id',
                'property_stock_journal',
                'property_account_income_categ_id',
                'property_account_expense_categ_id',
            ])
        scored = sorted(categories, key=completeness, reverse=True)
        for cat in scored:
            if completeness(cat) >= 4:
                return cat
        return Category

    def ff_action_use_existing_config(self):
        """Copy technical values from an existing well-configured category into
        the company-level configuration.

        Only fills values that are missing on the company; never overwrites an
        existing company configuration. Accounting managers only.
        """
        self._check_ff_manager()
        self.ensure_one()
        company = self.company_id
        category = self._ff_find_best_existing_category()
        if not category:
            raise ValidationError(
                _('No product category with automated valuation was found for '
                  'company %(company)s. Configure the technical accounts '
                  'manually.', company=company.name)
            )
        with_company = category.with_company(company)
        updates = {}
        mapping = {
            'ff_stock_valuation_account_id': 'property_stock_valuation_account_id',
            'ff_stock_input_account_id': 'property_stock_account_input_categ_id',
            'ff_stock_output_account_id': 'property_stock_account_output_categ_id',
            'ff_stock_journal_id': 'property_stock_journal',
            'ff_default_income_account_id': 'property_account_income_categ_id',
            'ff_default_cogs_account_id': 'property_account_expense_categ_id',
        }
        for company_fname, category_fname in mapping.items():
            if not company[company_fname] and with_company[category_fname]:
                updates[company_fname] = with_company[category_fname].id
        if not updates:
            raise ValidationError(
                _('Company %(company)s already has a complete simplified '
                  'inventory configuration. Nothing to initialize.',
                  company=company.name)
            )
        company.write(updates)
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    # -------------------------------------------------------------------------
    # Safe account creation (optional, explicit user action).
    # -------------------------------------------------------------------------
    def ff_action_create_technical_accounts(self):
        """Create the missing technical inventory accounts and journal for the
        current company (delegates to the shared company-level helper).

        - Never overwrites existing accounts / journals.
        - Generates collision-safe codes.
        - Uses the correct account types.
        - Creates company-specific records, clearly identified.
        Accounting managers only.
        """
        self._check_ff_manager()
        self.ensure_one()
        created = self.company_id._ff_ensure_technical_accounts()
        if not created:
            raise ValidationError(
                _('All technical inventory accounts and the stock journal are '
                  'already configured for company %(company)s.',
                  company=self.company_id.name)
            )
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
