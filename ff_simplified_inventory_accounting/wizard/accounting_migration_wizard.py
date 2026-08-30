# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FFAccountingMigrationWizard(models.TransientModel):
    """Wizard: 'Accounting / Valuation Migration'.

    Changing ``property_cost_method`` or ``property_valuation`` on a category
    with existing stock valuation history may trigger significant accounting
    consequences (Odoo empties and replenishes the stock, posting journal
    entries). This wizard inspects the impacted products before doing anything
    and blocks unsafe migrations.

    The actual migration is delegated to Odoo's native write() which handles
    Stock Valuation Layers and accounting entries correctly.
    """
    _name = 'ff.accounting.migration.wizard'
    _description = 'Accounting / Valuation Migration'

    category_ids = fields.Many2many(
        'product.category',
        string='Categories to migrate',
        required=True,
    )
    target_cost_method = fields.Selection(
        [('standard', 'Standard Price'),
         ('fifo', 'First In First Out (FIFO)'),
         ('average', 'Average Cost (AVCO)')],
        string='Target Costing Method',
    )
    target_valuation = fields.Selection(
        [('manual_periodic', 'Manual'),
         ('real_time', 'Automated')],
        string='Target Valuation Method',
    )

    # ---- Safety summary (refreshed on change) --------------------------------
    products_count = fields.Integer(string='Products', readonly=True)
    stock_quantity = fields.Float(string='Total Stock Quantity', readonly=True)
    svl_count = fields.Integer(string='Stock Valuation Layers', readonly=True)
    lot_valuated_count = fields.Integer(string='Lot/Serial Valuated Products', readonly=True)
    migration_safe = fields.Boolean(string='Safe to migrate', readonly=True)
    safety_message = fields.Text(string='Safety check', readonly=True)

    @api.onchange('category_ids', 'target_cost_method', 'target_valuation')
    def _onchange_refresh_safety(self):
        if not self.category_ids or not (self.target_cost_method or self.target_valuation):
            self.products_count = 0
            self.stock_quantity = 0.0
            self.svl_count = 0
            self.lot_valuated_count = 0
            self.migration_safe = False
            self.safety_message = _('Select at least one category and a target '
                                    'costing method or valuation method.')
            return
        products = self.env['product.product'].search([
            ('categ_id', 'in', self.category_ids.ids),
        ])
        self.products_count = len(products)
        self.stock_quantity = sum(p.qty_available for p in products)
        self.svl_count = self.env['stock.valuation.layer'].search_count([
            ('product_id', 'in', products.ids),
        ])
        lot_valuated = products.filtered(
            lambda p: p.lot_valuated and p.stock_valuation_layer_ids)
        self.lot_valuated_count = len(lot_valuated)

        if lot_valuated:
            self.migration_safe = False
            self.safety_message = _(
                'Migration is blocked: %(count)s product(s) are valuated by '
                'lot/serial number with existing valuation layers. Odoo cannot '
                'change the costing method of such products. Remove the '
                'valuation layers or change these products to non-lot '
                'valuation first.',
                count=len(lot_valuated),
            )
        elif self.stock_quantity:
            self.migration_safe = True
            self.safety_message = _(
                'Migration will be performed by Odoo: the current stock '
                '(%(qty)s units, %(svl)s valuation layers) will be emptied and '
                'replenished with the new method, generating the corresponding '
                'journal entries.',
                qty=round(self.stock_quantity, 2), svl=self.svl_count,
            )
        else:
            self.migration_safe = True
            self.safety_message = _(
                'No current stock for the selected categories. The migration '
                'will only change the category properties.'
            )

    def action_migrate(self):
        self.ensure_one()
        if not (self.target_cost_method or self.target_valuation):
            raise UserError(_('Select a target costing method or valuation '
                              'method before migrating.'))
        # Re-run the safety check in a fresh environment (onchange may not
        # reflect all records).
        for category in self.category_ids:
            products = self.env['product.product'].search([
                ('categ_id', '=', category.id),
            ])
            lot_valuated = products.filtered(
                lambda p: p.lot_valuated and p.stock_valuation_layer_ids)
            if lot_valuated:
                raise UserError(_(
                    'Migration is blocked for category %(category)s: '
                    '%(count)s product(s) are valuated by lot/serial number '
                    'with existing valuation layers.',
                    category=category.display_name, count=len(lot_valuated),
                ))
        vals = {}
        if self.target_cost_method:
            vals['property_cost_method'] = self.target_cost_method
        if self.target_valuation:
            vals['property_valuation'] = self.target_valuation
        self.category_ids.with_context(ff_skip_accounting_sync=True).write(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Accounting Migration'),
                'message': _('Costing / valuation method changed for '
                             '%(count)s categories.', count=len(self.category_ids)),
                'type': 'success',
                'sticky': False,
            },
        }
