"""
Database-backed behavioral test for FactEngagementAdminDashQueries.get_top_courses_by_engagement_query.

Exercises the actual query-builder output against a real MySQL table and asserts on the returned
business result (summed/rounded learning hours per course, ranking, multi-tenant filtering)
instead of asserting on the generated SQL string. See docs/adr/0001-... for the rationale.
"""
from enterprise_data.admin_analytics.database.queries.fact_engagement_admin_dash import FactEngagementAdminDashQueries
from enterprise_data.admin_analytics.database.query_filters import EqualQueryFilter, QueryFilters
from enterprise_data.tests.admin_analytics.sql_test_utils import AnalyticsSQLTestCase, skip_unless_mysql

ENTERPRISE_CUSTOMER_UUID = 'a92bc275-1067-4d4e-b8bd-4dbef27c1866'
OTHER_ENTERPRISE_CUSTOMER_UUID = 'b1f5e7b4-9f0e-4c8c-9b8d-2f6d5f7a1234'


@skip_unless_mysql()
class TestGetTopCoursesByEngagementQuery(AnalyticsSQLTestCase):
    """
    Behavioral tests for FactEngagementAdminDashQueries.get_top_courses_by_engagement_query.
    """
    table_name = 'fact_enrollment_engagement_day_admin_dash'
    table_ddl = """
        enterprise_customer_uuid VARCHAR(255),
        course_key VARCHAR(255),
        course_title VARCHAR(255),
        enroll_type VARCHAR(255),
        learning_time_seconds INT,
        activity_date DATE
    """

    def _filters(self):
        return QueryFilters([
            EqualQueryFilter(
                column='enterprise_customer_uuid',
                value_placeholder='enterprise_customer_uuid',
            ),
        ])

    def test_ranks_and_sums_learning_hours_per_course(self):
        # Two rows for course-1 on different dates: a test that only picked up the latest row
        # instead of aggregating both would produce a different, detectably wrong total.
        # course-2 has less total time, to prove ranking rather than just summation.
        # A row under a different enterprise customer proves the customer filter excludes it.
        self.insert_rows([
            {
                'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-1',
                'course_title': 'Course One',
                'enroll_type': 'verified',
                'learning_time_seconds': 3600,
                'activity_date': '2026-08-01',
            },
            {
                'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-1',
                'course_title': 'Course One',
                'enroll_type': 'verified',
                'learning_time_seconds': 3600,
                'activity_date': '2026-08-02',
            },
            {
                'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-2',
                'course_title': 'Course Two',
                'enroll_type': 'verified',
                'learning_time_seconds': 1800,
                'activity_date': '2026-08-01',
            },
            {
                'enterprise_customer_uuid': OTHER_ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-1',
                'course_title': 'Course One',
                'enroll_type': 'verified',
                'learning_time_seconds': 36000,
                'activity_date': '2026-08-01',
            },
        ])

        query = FactEngagementAdminDashQueries.get_top_courses_by_engagement_query(
            self._filters(), record_count=10,
        )
        results = self.run_production_query(
            query, params={'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID},
        )

        results_by_course = {row['course_key']: row for row in results}
        self.assertEqual(set(results_by_course), {'course-1', 'course-2'})
        # 3600 + 3600 seconds == 2.0 hours, summed across both course-1 rows.
        # ROUND() here rounds to the nearest whole hour (no decimal-place argument),
        # so course-2's 0.5h (1800 seconds) rounds up to 1.0.
        self.assertEqual(float(results_by_course['course-1']['learning_time_hours']), 2.0)
        self.assertEqual(float(results_by_course['course-2']['learning_time_hours']), 1.0)
        # course-1 (2.0h true total) should rank ahead of course-2 (0.5h true total),
        # even though both round to values where the difference is less obvious.
        self.assertEqual(results[0]['course_key'], 'course-1')

    def test_limits_to_top_n_courses_by_engagement(self):
        # course-3 is inserted first but has the least engagement, so a query builder that
        # simply took the first N inserted rows (rather than ranking by engagement) would
        # incorrectly include it while a correctly-ranked top-2 would not.
        self.insert_rows([
            {
                'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-3',
                'course_title': 'Course Three',
                'enroll_type': 'verified',
                'learning_time_seconds': 60,
                'activity_date': '2026-08-01',
            },
            {
                'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-1',
                'course_title': 'Course One',
                'enroll_type': 'verified',
                'learning_time_seconds': 36000,
                'activity_date': '2026-08-01',
            },
            {
                'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID,
                'course_key': 'course-2',
                'course_title': 'Course Two',
                'enroll_type': 'verified',
                'learning_time_seconds': 18000,
                'activity_date': '2026-08-01',
            },
        ])

        query = FactEngagementAdminDashQueries.get_top_courses_by_engagement_query(
            self._filters(), record_count=2,
        )
        results = self.run_production_query(
            query, params={'enterprise_customer_uuid': ENTERPRISE_CUSTOMER_UUID},
        )

        self.assertEqual(len(results), 2)
        self.assertEqual({row['course_key'] for row in results}, {'course-1', 'course-2'})
