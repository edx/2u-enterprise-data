"""
Unit tests for the sql_test_utils test helpers themselves.

These exercise validation logic that runs before any database connection is opened, so they
run regardless of whether a real MySQL server is available.
"""
import unittest

from enterprise_data.tests.admin_analytics.sql_test_utils import AnalyticsSQLTestCase, _is_safe_test_database_name


class TestIsSafeTestDatabaseName(unittest.TestCase):
    """
    Tests for _is_safe_test_database_name.
    """

    def test_accepts_test_prefixed_name(self):
        assert _is_safe_test_database_name('test_enterprise_data')

    def test_accepts_db_prefixed_name(self):
        assert _is_safe_test_database_name('db_default')

    def test_rejects_name_without_safe_prefix(self):
        assert not _is_safe_test_database_name('enterprise_data')


class TestInsertRowsValidation(unittest.TestCase):
    """
    Tests for AnalyticsSQLTestCase.insert_rows key validation.
    """

    def test_raises_on_mismatched_row_keys(self):
        instance = AnalyticsSQLTestCase.__new__(AnalyticsSQLTestCase)
        instance.table_name = 'irrelevant_for_this_test'
        with self.assertRaises(ValueError):
            instance.insert_rows([
                {'a': 1, 'b': 2},
                {'a': 1, 'c': 3},
            ])

    def test_empty_rows_is_a_noop(self):
        instance = AnalyticsSQLTestCase.__new__(AnalyticsSQLTestCase)
        instance.table_name = 'irrelevant_for_this_test'
        instance.insert_rows([])
