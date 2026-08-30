# ff_simplified_inventory_accounting

**Simplified Inventory Accounting for Odoo 18**

Makes product category accounting configuration as simple as in Odoo 19,
while keeping Odoo 18's native `stock_account` engine untouched.

On each product category the user only needs to choose:

- **Sales (Revenue) Account**
- **Cost of Goods Sold (COGS) Account**
- **Costing Method** (optional)

All technical inventory accounting properties (Stock Valuation Account,
Stock Interim Received, Stock Interim Delivered and the Stock Journal) are
configured **automatically** from a central per-company configuration.

The module only **configures Odoo**. Odoo creates the accounting entries.
There is **no duplicate accounting engine**.

## Repository structure

```
ff_simplified_inventory_accounting/   <- the Odoo module (add to addons_path)
├── __manifest__.py
├── models/
├── views/
├── wizard/
├── security/
├── tests/
├── i18n/
└── static/description/
```

## Compatibility

- Odoo **18.0** (Community & Enterprise)
- Python 3.10+
- Depends on `account`, `stock`, `stock_account`, `product`

## Installation

1. Copy the `ff_simplified_inventory_accounting` folder into your `addons_path`.
2. Update the apps list and install the module.

```bash
odoo -d DB_NAME -i ff_simplified_inventory_accounting --stop-after-init
```

Then configure under **Settings → Invoicing → Simplified Inventory Accounting**.

See the module `README.md` for full configuration and behavior details.

## Tests

```bash
odoo -d TEST_DB -i ff_simplified_inventory_accounting \
     --test-enable --test-tags=/ff_simplified_inventory_accounting --stop-after-init
```

## License

LGPL-3 — Flous Flow.
