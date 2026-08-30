# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class FFAccountingRepairWizard(models.TransientModel):
    """Wizard: 'Apply Simplified Accounting to Existing Categories'.

    Shows an audit summary of the current company's product categories and
    runs the Safe Accounting Repair (Mode A): fills missing accounts, syncs
    technical stock accounts with the company configuration and never changes
    the costing / valuation method.
    """
    _name = 'ff.accounting.repair.wizard'
    _description = 'Apply Simplified Accounting to Existing Categories'

    # -------------------------------------------------------------------------
    # Audit summary (computed for the current company)
    # -------------------------------------------------------------------------
    total_categories = fields.Integer(string='Total Categories', readonly=True)
    configured_count = fields.Integer(string='Configured', readonly=True)
    missing_income_count = fields.Integer(string='Missing Sales Account', readonly=True)
    missing_expense_count = fields.Integer(string='Missing COGS Account', readonly=True)
    missing_input_count = fields.Integer(string='Missing Stock Input', readonly=True)
    missing_output_count = fields.Integer(string='Missing Stock Output', readonly=True)
    missing_valuation_count = fields.Integer(string='Missing Stock Valuation', readonly=True)
    missing_journal_count = fields.Integer(string='Missing Stock Journal', readonly=True)
    manual_valuation_count = fields.Integer(string='Manual Valuation', readonly=True)
    diff_cost_method_count = fields.Integer(string='Different Costing Method', readonly=True)

    repair_info = fields.Text(string='Repair Plan', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super(FFAccountingRepairWizard, self).default_get(fields_list)
        company = self.env.company
        categories = self.env['product.category'].search([]).with_company(company)

        def count(predicate):
            return sum(1 for cat in categories if predicate(cat))

        res.update({
            'total_categories': len(categories),
            'configured_count': count(
                lambda c: c.property_valuation == 'real_time'
                and c.property_stock_account_input_categ_id
                and c.property_stock_account_output_categ_id
                and c.property_stock_valuation_account_id
                and c.property_stock_journal
                and c.property_account_income_categ_id
                and c.property_account_expense_categ_id
            ),
            'missing_income_count': count(lambda c: not c.property_account_income_categ_id),
            'missing_expense_count': count(lambda c: not c.property_account_expense_categ_id),
            'missing_input_count': count(
                lambda c: c.property_valuation == 'real_time'
                and not c.property_stock_account_input_categ_id
            ),
            'missing_output_count': count(
                lambda c: c.property_valuation == 'real_time'
                and not c.property_stock_account_output_categ_id
            ),
            'missing_valuation_count': count(
                lambda c: c.property_valuation == 'real_time'
                and not c.property_stock_valuation_account_id
            ),
            'missing_journal_count': count(
                lambda c: c.property_valuation == 'real_time'
                and not c.property_stock_journal
            ),
            'manual_valuation_count': count(
                lambda c: c.property_valuation == 'manual_periodic'
            ),
            'diff_cost_method_count': count(
                lambda c: company.ff_default_cost_method
                and c.property_cost_method != company.ff_default_cost_method
            ),
        })
        res['repair_info'] = _(
            'Safe repair will:\n'
            '- Fill missing Sales / COGS accounts (company defaults, keeping '
            'native category inheritance).\n'
            '- Fill missing technical stock accounts from the company '
            'configuration.\n'
            '- Never change the costing method or the valuation method.\n'
            '- Preserve intentionally selected category Sales / COGS accounts.'
        )
        return res

    # -------------------------------------------------------------------------
    # Mode A — Safe Accounting Repair
    # -------------------------------------------------------------------------
    def action_repair(self):
        self.ensure_one()
        company = self.env.company
        categories = self.env['product.category'].search([])
        category_count = 0
        changed_count = 0

        for category in categories:
            category_c = category.with_company(company)
            vals = {}
            # Fill missing Sales / COGS only when no ancestor provides a value
            # (native hierarchy preserved).
            if not category_c.property_account_income_categ_id \
                    and not category._ff_ancestor_has('property_account_income_categ_id') \
                    and company.ff_default_income_account_id:
                vals['property_account_income_categ_id'] = company.ff_default_income_account_id.id
            if not category_c.property_account_expense_categ_id \
                    and not category._ff_ancestor_has('property_account_expense_categ_id') \
                    and company.ff_default_cogs_account_id:
                vals['property_account_expense_categ_id'] = company.ff_default_cogs_account_id.id
            # Sync technical accounts with company configuration (Mode A).
            vals.update(company._ff_technical_vals())
            if vals:
                category_c.with_context(ff_skip_accounting_sync=True).write(vals)
                changed_count += 1
            category_count += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Safe Accounting Repair'),
                'message': _('%(changed)s of %(total)s categories were updated.',
                             changed=changed_count, total=category_count),
                'type': 'success',
                'sticky': False,
            },
        }
