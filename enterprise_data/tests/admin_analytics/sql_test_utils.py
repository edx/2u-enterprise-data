"""
Reusable helpers for database-backed behavioral tests of admin analytics raw SQL.

See docs/adr/0001-database-backed-behavioral-testing-for-admin-analytics-sql.md for the
rationale behind this pattern: tests here create controlled rows in a real MySQL table,
run the actual production query-builder + run_query, and assert on the returned business
result rather than on the generated SQL string.
"""
import unittest
from contextlib import closing

import mysql.connector

from django.conf import settings
from django.test import TestCase

from enterprise_data.admin_analytics.database.utils import get_db_connection, run_query


def _is_safe_test_database_name(name):
    """
    Return True if `name` looks like a database provisioned for tests, not a primary/dev schema.

    These tests run destructive DDL (CREATE TABLE, TRUNCATE, DROP TABLE) directly against
    `settings.DATABASES`, bypassing Django's test-database swapping. This is a last-resort
    guardrail against pointing that DDL at a real schema by mistake.
    """
    return name.startswith('test_') or name.startswith('db_')


def _mysql_available():
    """
    Return True if a connection can be opened to the configured reporting database and it is MySQL.
    """
    database = getattr(settings, 'ENTERPRISE_REPORTING_DB_ALIAS', 'default')
    if 'mysql' not in settings.DATABASES[database]['ENGINE']:
        return False
    if not _is_safe_test_database_name(settings.DATABASES[database]['NAME']):
        raise RuntimeError(
            f"Refusing to run destructive SQL behavioral tests against database "
            f"\"{settings.DATABASES[database]['NAME']}\": its name doesn't look like a test database "
            "(expected a \"test_\" or \"db_\" prefix). Point DB_NAME at a disposable test database."
        )
    try:
        with closing(get_db_connection(database)):
            return True
    except Exception:  # pylint: disable=broad-except
        return False


def skip_unless_mysql():
    """
    Class/method decorator-friendly skip condition for tests that require a real MySQL connection.

    Behavioral SQL tests are skipped (not failed) when no MySQL connection is available, e.g. the
    default local/SQLite test settings. They run automatically wherever MySQL is configured,
    including the mysql8-migrations CI workflow.
    """
    return unittest.skipUnless(_mysql_available(), 'A MySQL connection is required for this behavioral SQL test.')


class AnalyticsSQLTestCase(TestCase):
    """
    Base test case for database-backed behavioral tests of admin analytics raw SQL.

    Subclasses must set:
        table_name (str): name of the test-owned analytics table.
        table_ddl (str): column definitions to place inside `CREATE TABLE {table_name} (...)`.
            This is test-owned DDL, not a copy of a Django migration -- keep it minimal, limited
            to the columns the query builder under test actually reads or filters on.

    Usage:
        class TestSomeQuery(AnalyticsSQLTestCase):
            table_name = 'fact_enrollment_engagement_day_admin_dash'
            table_ddl = '''
                enterprise_customer_uuid VARCHAR(255),
                course_key VARCHAR(255),
                learning_time_seconds INT,
                is_engaged INT
            '''

            def test_something(self):
                self.insert_rows([{...}, {...}])
                query = SomeQueries.get_something_query(filters)
                results = self.run_production_query(query, params={...})
                self.assertEqual(results, [...])
    """
    table_name = None
    table_ddl = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not _mysql_available():
            raise unittest.SkipTest('A MySQL connection is required for this behavioral SQL test.')
        if cls.table_name is None or cls.table_ddl is None:
            raise NotImplementedError('AnalyticsSQLTestCase subclasses must set table_name and table_ddl.')
        with closing(get_db_connection()) as connection:
            with closing(connection.cursor()) as cursor:
                try:
                    cursor.execute(f'CREATE TABLE {cls.table_name} ({cls.table_ddl})')
                except mysql.connector.errors.ProgrammingError as exc:
                    if exc.errno == mysql.connector.errorcode.ER_TABLE_EXISTS_ERROR:
                        raise RuntimeError(
                            f'Table "{cls.table_name}" already exists on the database configured for '
                            f'{cls.__name__}. Refusing to run: this test truncates and drops its table, '
                            'and reusing a pre-existing table risks destroying real data if these tests '
                            'are ever pointed at a non-test database.'
                        ) from exc
                    raise
            connection.commit()

    @classmethod
    def tearDownClass(cls):
        if _mysql_available() and cls.table_name:
            with closing(get_db_connection()) as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute(f'DROP TABLE IF EXISTS {cls.table_name}')
                connection.commit()
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        if _mysql_available() and self.table_name:
            with closing(get_db_connection()) as connection:
                with closing(connection.cursor()) as cursor:
                    cursor.execute(f'TRUNCATE TABLE {self.table_name}')
                connection.commit()

    def insert_rows(self, rows):
        """
        Insert controlled rows into the test-owned table.

        Arguments:
            rows (list[dict]): each dict maps column name to value; all dicts must share the
                same set of keys.
        """
        if not rows:
            return
        columns = list(rows[0].keys())
        for row in rows:
            if row.keys() != rows[0].keys():
                raise ValueError(
                    f'All row dicts passed to insert_rows must share the same keys. '
                    f'Expected {sorted(rows[0].keys())}, got {sorted(row.keys())}.'
                )
        column_list = ', '.join(columns)
        placeholders = ', '.join(['%s'] * len(columns))
        values = [tuple(row[column] for column in columns) for row in rows]
        with closing(get_db_connection()) as connection:
            with closing(connection.cursor()) as cursor:
                cursor.executemany(
                    f'INSERT INTO {self.table_name} ({column_list}) VALUES ({placeholders})',
                    values,
                )
            connection.commit()

    def run_production_query(self, query, params=None, as_dict=True):
        """
        Execute a production query-builder's SQL through the actual `run_query` helper.

        Arguments:
            query (str): SQL produced by a production query-builder method.
            params (dict): named (%(name)s-style) parameters forwarded to `run_query`.
            as_dict (bool): when True (default), return rows as dicts keyed by column name.
        """
        return run_query(query, params=params, as_dict=as_dict)
