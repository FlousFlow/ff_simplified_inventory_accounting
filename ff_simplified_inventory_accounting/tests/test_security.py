# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError

from .common import FFTestCommon


class TestSecurity(FFTestCommon):
    """Security: sensitive actions and data are restricted to accounting
    managers, and company configuration never leaks between companies."""

    @classmethod
    def setUpClass(cls):
        super(TestSecurity, cls).setUpClass()
        cls.manager_group = cls.env.ref('account.group_account_manager')
        # A normal internal user WITHOUT the accounting manager group.
        cls.regular_user = cls.env['res.users'].create({
            'name': 'FF Regular User',
            'login': 'ff_regular_%s' % cls.__name__,
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
            'company_id': cls.company.id,
            'company_ids': [(6, 0, cls.company.ids)],
        })

    def _as_regular(self):
        """Environment running as a non-manager user (su=False)."""
        return self.env(
            user=self.regular_user.id,
            context={**self.env.context, 'allowed_company_ids': self.company.ids},
        )

    # ---------------------------------------------------------------------
    # Access to the admin wizards is manager-only
    # ---------------------------------------------------------------------
    def test_20_non_manager_cannot_access_repair_wizard(self):
        self.assertFalse(self.regular_user.has_group('account.group_account_manager'),
                         'Test precondition: regular user must not be a manager')
        with self.assertRaises(AccessError):
            self._as_regular()['ff.accounting.repair.wizard'].create({})

    def test_21_non_manager_cannot_access_migration_wizard(self):
        with self.assertRaises(AccessError):
            self._as_regular()['ff.accounting.migration.wizard'].create({})

    def test_22_manager_can_access_wizards(self):
        # The test environment (superuser) can create both wizards.
        self.env['ff.accounting.repair.wizard'].create({})
        self.env['ff.accounting.migration.wizard'].create({})

    # ---------------------------------------------------------------------
    # Sensitive settings methods are manager-only (defense in depth)
    # ---------------------------------------------------------------------
    def test_23_non_manager_cannot_create_technical_accounts(self):
        self._enable_feature()
        # The manager creates the settings record (regular users cannot).
        settings = self.env['res.config.settings'].create({
            'ff_simplified_inventory_accounting': True,
        })
        # A non-manager calling the sensitive method must be denied.
        with self.assertRaises(AccessError):
            settings.with_user(self.regular_user.id).ff_action_create_technical_accounts()

    def test_24_non_manager_cannot_use_existing_config(self):
        settings = self.env['res.config.settings'].create({})
        with self.assertRaises(AccessError):
            settings.with_user(self.regular_user.id).ff_action_use_existing_config()

    # ---------------------------------------------------------------------
    # Health-check action is manager-only
    # ---------------------------------------------------------------------
    def test_25_health_check_action_is_manager_only(self):
        action = self.env.ref(
            'ff_simplified_inventory_accounting.action_inventory_accounting_health')
        self.assertIn(self.manager_group, action.groups_id,
                      'Health check action must be restricted to accounting managers')

    # ---------------------------------------------------------------------
    # Multi-company isolation (no leakage)
    # ---------------------------------------------------------------------
    def test_26_company_config_does_not_leak(self):
        self._enable_feature()
        company_b = self.env['res.company'].create({
            'name': 'FF Security Co B', 'currency_id': self.currency.id,
        })
        category = self.env['product.category'].with_company(self.company).create({
            'name': 'Security Cat', 'parent_id': False,
        })
        # Configured under company A.
        a_view = category.with_company(self.company)
        self.assertEqual(a_view.property_stock_valuation_account_id,
                         self.stock_valuation_account)
        self.assertEqual(a_view.property_stock_journal, self.stock_journal)
        # No leakage into company B.
        b_view = category.with_company(company_b)
        self.assertFalse(b_view.property_stock_valuation_account_id,
                         'Company A accounts must not leak into company B')
        self.assertFalse(b_view.property_stock_journal)

    # ---------------------------------------------------------------------
    # SQL helper is whitelist-protected against injection
    # ---------------------------------------------------------------------
    def test_27_sql_helper_rejects_unknown_fields(self):
        company = self.company
        # A whitelisted field returns a valid list of category ids.
        self.assertTrue(isinstance(
            company._ff_category_ids_without_stored('property_cost_method'), list))
        # Anything not on the whitelist returns an empty list (no SQL injected).
        self.assertEqual(company._ff_category_ids_without_stored(
            "property_cost_method'; DROP TABLE product_category; --"), [])
        self.assertEqual(company._ff_category_ids_without_stored('nonexistent'), [])
