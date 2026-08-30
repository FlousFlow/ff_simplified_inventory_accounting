# -*- coding: utf-8 -*-


def post_init_hook(env):
    """Auto-configure the whole product category tree after installation.

    - Creates the technical inventory accounts + the stock journal.
    - Fills Sales / COGS defaults from the standard chart.
    - Enables the feature.
    - Applies the configuration to every existing product category so that
      stock moves (receipts, deliveries, inventory adjustments) produce the
      correct native accounting entries with no manual intervention.

    The only manual input left is choosing Sales / COGS accounts when the
    defaults need to change.
    """
    if not env['account.account'].search_count([]):
        # No chart of accounts yet: nothing safe to configure.
        return
    for company in env['res.company'].search([]):
        company._ff_auto_setup()
