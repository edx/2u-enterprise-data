# 0001. Database-backed behavioral testing for admin analytics raw SQL

Date: 2026-08-18

## Status

Accepted

Ticket: ENT-12151
Reviewers: Ramya Gopal Rao / Enterprise Engineering Team
Related: ENT-12151-raw-sql-to-orm-and-testing-strategy.md (covers a separate decision under the same ticket — converting the single `MAX(created)` lookup in `fetch_max_enrollment_datetime` to Django ORM. This ADR does not supersede that one; it addresses the remaining, complex raw SQL that stays raw SQL.)

## Context

`edx-enterprise-data` contains raw SQL used by admin analytics, primarily under `enterprise_data/admin_analytics/database/queries/`. The main query modules are:

- `fact_engagement_admin_dash.py`
- `fact_enrollment_admin_dash.py`
- `skills_daily_rollup_admin_dash.py`

These queries contain business logic including filtering, grouping, aggregation, counting, learning-time calculations, and rounding. They are executed through `enterprise_data/admin_analytics/database/utils.py`, using `run_query()` and `get_db_connection()`. The database connection uses `settings.ENTERPRISE_REPORTING_DB_ALIAS` and connects to the enterprise reporting MySQL database.

Historically, some tests have asserted that a particular SQL string is generated or passed to `run_query()`. These tests validate query structure but do not prove that the SQL produces the correct business result. A SQL query can remain syntactically valid while still returning an incorrect value. For example, assertions that verify the presence of `GROUP BY`, `SUM`, or `ROUND` cannot reliably detect:

- aggregation occurring at the wrong level,
- rounding happening before or after the wrong aggregation,
- incorrect grouping dimensions,
- missing filters,
- incorrect session counts,
- or an incorrect final business result.

The previous learning-hours regression demonstrated this problem. A behavioral test that creates controlled database data, executes the actual production SQL, and validates the resulting learning-hours value provides stronger regression protection.

ENT-12151 needs to establish a reusable pattern for testing business logic implemented in raw SQL. The ticket acceptance criteria require the team to: decide where SQL execution belongs in the testing stack; research approaches for testing raw SQL and document the selected approach in an ADR; and write or refactor at least one SQL logic test using the selected pattern.

## Decision

For business-critical raw SQL under `enterprise_data/admin_analytics/database/queries/`, we will use database-backed behavioral testing as the preferred testing pattern.

The testing flow is:

```
Controlled test data
→ Actual production query builder
→ Actual production run_query execution
→ MySQL test database
→ Assert the expected business result
```

Tests validate the returned business result instead of depending primarily on the exact SQL string.

**Reusable testing pattern.** A reusable test utility is provided under `enterprise_data/tests/admin_analytics/sql_test_utils.py` (`AnalyticsSQLTestCase`, `skip_unless_mysql`). It supports:

1. Create the required analytics table in the test MySQL database (test-owned DDL via `table_ddl`).
2. Insert controlled rows for the business scenario being tested (`insert_rows`).
3. Call the actual production query-builder method.
4. Execute the resulting SQL using the production `run_query` helper (`run_production_query`).
5. Assert the returned business result.
6. Clean up the table after the tests complete (`TRUNCATE` between tests, `DROP TABLE` in `tearDownClass`).

The test-owned table DDL allows analytics queries to be exercised without requiring Django models or migrations for reporting tables.

**Delivered example.** `enterprise_data/tests/admin_analytics/test_fact_engagement_queries_sql.py` implements `TestGetTopCoursesByEngagementQuery`, a behavioral test for `FactEngagementAdminDashQueries.get_top_courses_by_engagement_query`, satisfying AC #3:

- `test_ranks_and_sums_learning_hours_per_course` inserts rows across two courses and two enterprise customers, then asserts that the query sums per-course learning time correctly, converts it to rounded hours, ranks by total engagement, and excludes rows belonging to a different enterprise customer.
- `test_limits_to_top_n_courses_by_engagement` asserts `record_count` limits the result to the top N courses ranked by engagement, not simply the first N rows inserted.

Both tests exercise the real query-builder output against a real MySQL table and assert on the returned business result, rather than mocking `run_query`'s return value or asserting on the SQL string.

**Example test flow (for future tests).**

- *Arrange* — create controlled records designed to exercise the specific business behavior: multiple learners, different learning-time values, engaged and non-engaged records, values that expose rounding differences, records that should and should not pass filters.
- *Act* — call the actual production query builder (e.g. `FactEngagementAdminDashQueries.get_learning_hours_and_daily_sessions_query(...)`) and execute the generated SQL using the actual `run_query` implementation. Note `get_learning_hours_and_daily_sessions_query` exists as a distinct method on both `FactEngagementAdminDashQueries` and `FactEnrollmentAdminDashQueries` (same method name, different classes, different query bodies) — future tests should call it on the class under test, not assume there is only one such method.
- *Assert* — validate the returned values, such as learning hours, sessions, engagement count, grouped values, filtered results, or aggregated totals. The assertion should focus on the business result rather than the exact formatting of the SQL.

**Parameter binding.** `run_production_query` (`AnalyticsSQLTestCase.run_production_query`) forwards its `params` argument directly to the production `run_query(query, params=None, as_dict=False)` helper in `enterprise_data/admin_analytics/database/utils.py`, which passes it to `cursor.execute(query, params=params)`. `params` is a dict of `%(name)s`-style named placeholders, not a positional tuple.

Two of the filter classes under `enterprise_data/admin_analytics/database/query_filters/` can emit either literal SQL or a named placeholder, depending on which constructor argument is supplied:

- `EqualQueryFilter(column, value=...)` inlines the value as a SQL literal via `value_to_sql` (strings are wrapped in quotes). This is what `TestGetTopCoursesByEngagementQuery` uses today.
- `EqualQueryFilter(column, value_placeholder=...)` emits `column = %(name)s` instead, leaving the value to be supplied at execution time.

The same `value`/`*_placeholder` split exists on `ComparisonQueryFilter`, `BetweenQueryFilter` (`_range` vs `range_placeholders`), and `INQueryFilter` (`values` vs `values_placeholders`). `NULLQueryFilter` takes no value at all.

Prefer the placeholder form plus `params=` in new behavioral tests, for the same reason parameterized queries are preferred in production code: it exercises the actual binding path used against real user-controlled input (dates, UUIDs, lists of course keys) rather than only the string-literal path, and it avoids reimplementing `value_to_sql`'s quoting/escaping rules by hand in test data. Example:

```python
filters = QueryFilters([
    EqualQueryFilter(column='enterprise_customer_uuid', value_placeholder='enterprise_customer_uuid'),
])
query = FactEngagementAdminDashQueries.get_top_courses_by_engagement_query(filters, record_count=10)
results = self.run_production_query(
    query,
    params={'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID},
)
```

Using the literal `value=` form is acceptable when a test is deliberately only exercising the query builder's structure (e.g. a fixed constant that will never come from user input), but new tests that stand in for real filter values (customer UUIDs, date ranges, course-key lists) should bind them as params rather than string-interpolating them into the filter.

**`QueryFilters.to_sql()` usage.** `QueryFilters` (in `enterprise_data/admin_analytics/database/query_filters/base.py`) is a list subclass of `QueryFilter` instances; its `to_sql()` joins each filter's own `to_sql()` with `AND`. Behavioral tests should build filters the same way production code does — construct the `QueryFilter` subclasses the query-builder method expects, pass the resulting `QueryFilters` instance into the production query-builder method, and let the query builder call `to_sql()` internally. Do not call `to_sql()` in the test and then hand-edit or re-parse the resulting string — that reintroduces a string-based assertion path and defeats the purpose of behavioral testing. `to_sql()` should only ever be invoked by the production query-builder code, never asserted on directly by a test.

An empty `QueryFilters()` produces an empty string, not `1=1` or similar; a query builder that unconditionally appends `WHERE {filters.to_sql()}` will emit invalid SQL (`WHERE` with nothing after it) if called with no filters. Behavioral tests for query builders that accept optional filters should include a case with an empty `QueryFilters([])` to confirm the query builder itself guards against this, since `QueryFilters` does not.

**Test data design and isolation.** Design test data to make the specific business rule observable, not just to have some rows in the table. `test_ranks_and_sums_learning_hours_per_course` is the model: it inserts two rows for one course on different dates specifically so a query that summed incorrectly (e.g. only picked up the latest row instead of aggregating) would produce a different, detectably wrong number. Rows for a second course exist to prove ranking, not just summation, and a row under a different `enterprise_customer_uuid` exists to prove the customer filter actually excludes rows rather than merely being present in the SQL text.

When adding new behavioral tests, include analogous "control" rows: values that would produce the correct answer if the logic were subtly wrong (off-by-one grouping, wrong join, filter forgotten), not only values that happen to produce the correct answer under the intended logic.

Test isolation relies on `AnalyticsSQLTestCase`: `setUpClass` creates the table once, `setUp` truncates it before every test method, and `tearDownClass` drops it. This means:

- Tests within one `TestCase` subclass share a table but never share rows — `TRUNCATE` runs before each test, so tests cannot leak data to one another regardless of order.
- Tests must not assume any pre-existing data; only rows inserted via `insert_rows` within that test (or its own `setUp` override) should be relied upon.
- Because MySQL's test database is a real shared resource, tests that run concurrently against the same physical table name from two different `TestCase` subclasses (e.g. two subclasses both testing the same underlying table) could `TRUNCATE` out from under each other if the test runner parallelizes at the process level. Existing tests avoid this by having one `AnalyticsSQLTestCase` subclass own each `table_name`; keep that one-subclass-per-table convention for new tests, or coordinate on a `setUpClass`/`tearDownClass` isolation strategy (e.g. a per-class table name suffix) if a second suite needs the same underlying table.

**`table_ddl` maintenance responsibility.** `table_ddl` on an `AnalyticsSQLTestCase` subclass is test-owned DDL, not a copy of a Django migration — there is no migration for these reporting tables to copy from, and none is created by this pattern. This has a direct consequence: the DDL and the real reporting table's schema can drift, since nothing mechanically keeps them in sync. If a column is added, renamed, or retyped in the actual `ENTERPRISE_REPORTING_DB_ALIAS` reporting table (by whatever process populates it), the corresponding `table_ddl` in the test suite must be updated by hand, or the behavioral test will either silently miss a newly-relevant column or, in the worse case, keep passing against a schema that no longer matches production and give false confidence.

Practical guidance for whoever changes a reporting table's schema or adds a new behavioral test:

- Keep `table_ddl` minimal — only the columns the query builder under test actually reads or filters on — rather than mirroring the full production schema, so there's less to keep in sync and less ambiguity about which columns matter to the test.
- When changing a production reporting table's shape (new column consumed by a query builder, type change, renamed column), update every `table_ddl` in `enterprise_data/tests/admin_analytics/` that targets that table in the same change.
- There is currently no automated check that `table_ddl` matches the real reporting table's schema; this is a manual responsibility of the PR author. If drift becomes a recurring problem, a follow-up could add a CI check that diffs `table_ddl` against `INFORMATION_SCHEMA.COLUMNS` for the real table, but that is not part of this ADR's scope.

**Future SQL-test prioritization.** Not all raw SQL under `enterprise_data/admin_analytics/database/queries/` needs a behavioral test at once. Prioritize in roughly this order:

1. Queries with a documented regression history (e.g. the learning-hours calculation that motivated this ADR) — these have already demonstrated that a SQL-string test was insufficient.
2. Queries containing arithmetic, rounding, or unit conversion (`ROUND`, division for seconds→hours, averages) — these are the cases where a syntactically valid query most easily returns a silently wrong number.
3. Queries with ranking/limiting behavior (`ORDER BY` + `LIMIT`/`record_count`) — easy to get right for the first N rows inserted and wrong for the general case, as `test_limits_to_top_n_courses_by_engagement` demonstrates.
4. Queries with multi-tenant filtering (`enterprise_customer_uuid` and similar) — a missing or malformed filter here is a data-leak bug, not just an incorrect number.
5. Simple pass-through queries (a single `SELECT` with no aggregation, grouping, or derived columns) — lowest priority for behavioral coverage; a structural/SQL-string check or none at all may be sufficient.

`FactEnrollmentAdminDashQueries` and `SkillsDailyRollupAdminDashQueries` currently have no behavioral tests under this pattern (only `FactEngagementAdminDashQueries.get_top_courses_by_engagement_query` does). They are the natural next candidates, prioritized using the list above — in particular, both modules' `get_learning_hours_and_daily_sessions_query` methods (present on more than one class) are aggregation/rounding queries and should be covered before simpler pass-through queries in the same modules.

**Testing stack placement.** These SQL behavioral tests run in the normal automated CI workflow where a real MySQL test connection is available. `.github/workflows/mysql8-migrations.yml` adds a "Run SQL behavioral tests" step that runs `pytest enterprise_data/tests/admin_analytics/test_fact_engagement_queries_sql.py -v` against the MySQL 8 service the workflow already provisions.

Follow-up needed: the CI step matches `test_*_sql.py` rather than naming a single test file, so new behavioral test files added under `enterprise_data/tests/admin_analytics/` following this naming convention are picked up automatically without further workflow changes.

The reusable helper (`skip_unless_mysql` / `_mysql_available`) detects whether a MySQL connection can be opened and skips the behavioral tests when one is not available. This allows developers using a MySQL environment to run the tests locally, MySQL-backed CI jobs to run them automatically, and environments that only provide SQLite or do not configure the reporting database to skip them safely.

Note the skip check only verifies that a connection can be opened — it does not verify that the target schema/credentials are otherwise correct. A reachable MySQL instance with the wrong database or missing grants will not be skipped; it will attempt to run and fail with a connector error rather than skip. This is an acceptable trade-off (it surfaces genuine misconfiguration instead of hiding it), but reviewers should not read "skips safely" as "never fails for infrastructure reasons."

The intent is to obtain automated regression protection rather than relying primarily on manual SQL verification.

## Alternatives Considered

- **SQL string assertions** — not selected as the primary approach. Lightweight, fast, easy to implement, but validate structure instead of behavior; brittle when SQL formatting changes; cannot reliably detect incorrect aggregation, grouping, filtering, or rounding behavior. Checking that `GROUP BY`, `ROUND`, or a table name appears does not prove the query produces the correct result. An existing example remains in the codebase: `enterprise_data/tests/api/v1/views/test_enterprise_admin.py` defines `_mock_run_query`, a dict keyed by literal SQL query strings, patched onto `run_query` for `fact_engagement_admin_dash`, `fact_enrollment_admin_dash`, and `skills_daily_rollup_admin_dash` at the view/API level. This ADR does not require that test to be migrated — it validates view-level wiring rather than SQL business logic — but it is a candidate for future migration to the behavioral pattern if its assertions ever need to cover business results rather than request/response plumbing.
- **Convert all analytics queries to Django ORM** — rejected. Some analytics reporting tables do not have Django models, and complex analytics logic may be clearer in SQL. Converting all SQL to ORM would significantly increase the scope of this ticket without eliminating the need to test business behavior. (Django ORM remains appropriate for simple queries where a Django model already exists and raw SQL provides no additional value — see the separate `SELECT MAX(created) FROM enterprise_learner_enrollment` decision in ENT-12151-raw-sql-to-orm-and-testing-strategy.md. ORM conversion is not the general testing strategy established by this ADR; complex analytics SQL does not need to be rewritten into ORM solely for testability.)
- **SQLAlchemy** — rejected. It would introduce an additional architectural abstraction without providing enough benefit for this testing problem: the repository already uses Django ORM for model-backed data, existing analytics SQL would need to be rewritten, and complex SQL business behavior would still need behavioral validation regardless.
- **django-snowflake** — rejected. The SQL targeted by this ticket is MySQL-backed admin analytics SQL under `enterprise_data/admin_analytics/database/queries/`. Snowflake belongs to a separate LPR data-access path (`enterprise_data/api/v1/views/lpr_data_source_snowflake.py` and its consumer `enterprise_data/api/v1/views/enterprise_learner.py`, using `snowflake-connector-python` and private-key authentication) and is explicitly out of scope for this ADR. Introducing `django-snowflake` would require adopting an additional Django database backend and potentially creating Django models for Snowflake tables, with no direct benefit to the reusable MySQL testing pattern established here. The database-backed pattern selected in this ADR relies on a real MySQL database that can be provided locally or in CI; there is no equivalent local Snowflake database available. Snowflake query testing should be handled separately (e.g. connector/cursor mocking or an appropriate integration environment) if additional coverage is required.
- **Manual / local SQL testing only** — rejected as the default strategy. Useful during debugging, but provides no continuous regression protection. Where practical, SQL behavior should be exercised automatically in MySQL-backed CI.
- **Test database choice: SQLite vs. MySQL** — SQLite was rejected for the behavioral test database. Integer division, `ROUND` behavior, and date/aggregate semantics can differ between SQLite and MySQL, so a test passing against SQLite is not evidence that the production MySQL query behaves the same way. MySQL is used because it matches the production execution path. When no real MySQL connection is configured (e.g. a contributor running default local/SQLite test settings), `skip_unless_mysql` skips these tests rather than failing or falling back to SQLite — keeping the default local test run fast and green, while CI's MySQL 8 workflow (and any developer who points `DB_ENGINE` at MySQL locally) gets full behavioral coverage.

## Consequences

**Easier:**

- Business logic embedded in raw analytics SQL (aggregation, rounding, ranking, multi-tenant filtering) gets real regression protection instead of structural SQL-string checks that can pass while the result is wrong.
- Future behavioral tests are cheaper to write: `AnalyticsSQLTestCase` / `skip_unless_mysql` handle table setup, teardown, and MySQL-availability skipping, so new tests only need to define DDL, insert rows, and assert on results.
- New behavioral test files following the `test_*_sql.py` naming convention under `enterprise_data/tests/admin_analytics/` are picked up automatically by the MySQL 8 CI workflow, with no further workflow changes required.
- The pattern exercises the actual production query builder and `run_query` execution path, including real parameter binding via `value_placeholder`/`params`, rather than reimplementing quoting/escaping logic in test data.

**Harder / accepted trade-offs:**

- These tests require a real MySQL connection; they are skipped (not run, not failed) in environments without one, including default local/SQLite test runs. This means a contributor running the default local suite gets no signal from these tests — full coverage depends on CI's MySQL 8 workflow or a developer manually pointing `DB_ENGINE` at MySQL.
- The skip check only verifies that a MySQL connection can be opened, not that the target schema/credentials are correct. A misconfigured-but-reachable MySQL instance will attempt to run and fail with a connector error rather than skip — an accepted trade-off since it surfaces misconfiguration rather than hiding it.
- `table_ddl` in each test is hand-maintained and not mechanically kept in sync with the real reporting table's schema (there is no migration to generate it from). Schema drift (added/renamed/retyped columns) must be caught manually by whoever changes the production reporting table or adds a new test; there is currently no automated diff against `INFORMATION_SCHEMA.COLUMNS`. This is called out as a known gap, with a possible future CI check noted as out of scope for this ADR.
- Not all raw SQL under `enterprise_data/admin_analytics/database/queries/` has behavioral coverage yet — only `FactEngagementAdminDashQueries.get_top_courses_by_engagement_query` does today. `FactEnrollmentAdminDashQueries` and `SkillsDailyRollupAdminDashQueries` have none; the prioritization list in this ADR should guide which queries get covered next (regression history → arithmetic/rounding → ranking/limiting → multi-tenant filtering → simple pass-through).
- Snowflake-backed LPR data sources remain untested by this pattern and need a separate strategy if coverage is required there (open follow-up, not resolved by this ADR).

**Revisit if:** `table_ddl` drift causes a false-positive (a test keeps passing against a schema that no longer matches production), which would be the trigger to prioritize an automated `table_ddl`-vs-`INFORMATION_SCHEMA` CI check; or if Snowflake-backed LPR queries need regression protection, which would require a separate, non-MySQL testing strategy.

## Acceptance Criteria

- [x] Decided where SQL execution belongs in the testing stack: database-backed behavioral tests against real MySQL, run automatically in the MySQL 8 CI workflow, skipped elsewhere.
- [x] Researched alternatives (SQL string assertions, full ORM conversion, SQLAlchemy, django-snowflake, manual testing) and documented the selected approach in this ADR.
- [x] Wrote a SQL logic test using the selected pattern: `TestGetTopCoursesByEngagementQuery` in `enterprise_data/tests/admin_analytics/test_fact_engagement_queries_sql.py`.
- [x] Provided a reusable test utility (`sql_test_utils.py`) so future behavioral tests do not reimplement table setup/teardown/skip logic.
- [x] Updated the CI step in `.github/workflows/mysql8-migrations.yml` to match `test_*_sql.py` so future behavioral SQL test files are picked up automatically.
- [ ] Follow-up (optional): decide whether Snowflake-backed LPR queries need their own test strategy.
