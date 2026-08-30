# Simplified Inventory Accounting

Makes product category accounting configuration as simple as in Odoo 19, while
keeping **Odoo 18's native `stock_account` engine untouched**.

On each product category the user only needs to choose:

- **Sales (Revenue) Account**
- **Cost of Goods Sold (COGS) Account**
- **Costing Method** (optional)

All technical inventory accounting properties (Stock Valuation Account, Stock
Interim Received, Stock Interim Delivered and the Stock Journal) are configured
**automatically** from a central per-company configuration.

The module only **configures Odoo**. Odoo creates the accounting entries.
There is **no duplicate accounting engine**.

---

## What it solves

| Before (Odoo 18) | After (this module) |
|---|---|
| Income, Expense, Inventory Valuation, Costing Method, Stock Journal, Stock Input, Stock Output, Stock Valuation — all on the category form | Category Name, Sales Account, Cost of Goods Sold, Costing Method |
| Missing technical accounts cause wrong stock valuation | Technical accounts always come from the company configuration |
| Hard to audit which categories are misconfigured | Accounting Status + Health Check screen |

---

## Installation

1. Copy the `ff_simplified_inventory_accounting` folder into your `addons_path`.
2. Update the apps list and install the module (requires `account`, `stock`,
   `stock_account`, `product`).

```bash
odoo -d DB_NAME -i ff_simplified_inventory_accounting --stop-after-init
```

> On install the module does **not** rewrite any existing category. You choose
> when to apply it.

---

## Configuration (per company)

Open **Settings → Invoicing → Simplified Inventory Accounting**.

1. **User Defaults**
   - Default Sales Account
   - Default Cost of Goods Sold Account
   - Default Costing Method (Standard / AVCO / FIFO)
2. **Advanced Technical Configuration** (accounting managers only)
   - Stock Valuation Account
   - Stock Interim Received Account
   - Stock Interim Delivered Account
   - Stock Journal
   - Buttons: *Use Existing Inventory Accounting Configuration* (copies from an
     existing well-configured category) and *Create Technical Inventory
     Accounts* (creates the missing accounts + stock journal with
     collision-safe codes).

3. Tick **Enable Simplified Inventory Accounting** and save.

**Validation:** you cannot enable the feature while required values are
missing — a clear error tells you exactly what is missing.

---

## How it behaves

- **New categories** (created through the UI, CSV import, XML-RPC, JSON-RPC or
  any ORM call) automatically receive:
  - Sales / COGS from the company defaults (an explicit choice is preserved,
    and the native category hierarchy for Income/Expense is kept);
  - `Inventory Valuation = Automated (real_time)`;
  - the company Costing Method (an explicit choice is preserved);
  - the company technical accounts and stock journal.
- **Existing categories** can be aligned through the administrative action
  **Apply Simplified Accounting to Existing Categories** (safe repair: fills
  missing values and syncs technical accounts; never changes costing method).
- **Costing / Valuation migration** is a separate, guarded action
  (**Accounting / Valuation Migration**) that inspects products, quantities,
  valuation layers and lot valuation first, blocks unsafe migrations, and
  delegates the actual change to Odoo's native mechanism.
- **Auto-heal:** writing a category with Automated valuation restores any
  missing technical property from the company configuration.
- **Accounting Status** on the category: `Configured`, `Custom` (valid but
  different Sales/COGS from company defaults) or `Warning` (missing settings).
- **Inventory Accounting Health Check** screen lists every category with its
  status, Sales/COGS/Costing/Valuation and (for managers) the technical
  accounts, with filters for missing accounts, manual valuation, custom
  accounting and healthy.

---

## Multi-company

The configuration is stored per company. Two companies can use different
accounts, journals and cost methods for the same product category. Company
values never leak into another company.

---

## Accounting behavior (unchanged from Odoo)

The standard flows keep working exactly as Odoo does natively:

```
Purchase Order → Receipt → Stock Valuation Layer → native Inventory Journal Entry → Vendor Bill
Sales Order   → Delivery → Stock Valuation Layer → native Inventory Accounting → Customer Invoice → Revenue / COGS
```

The module guarantees the category is correctly configured so these flows
produce the right entries with no duplicates.

---

## Tests

Automated tests cover: new category defaults, custom accounts, safe repair,
batch/import creation, historical categories, receipt, vendor bill, delivery,
customer invoice + COGS (anglo-saxon), sales return, purchase return,
multi-company isolation, settings validation and migration safety.

```bash
odoo -d TEST_DB -i ff_simplified_inventory_accounting \
     --test-enable --test-tags=/ff_simplified_inventory_accounting --stop-after-init
```

---

## License

LGPL-3 — Flous Flow.
