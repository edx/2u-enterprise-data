"""
Test the utility functions in the admin_analytics app for data loading operations.
"""
from datetime import datetime

from mock import patch

from django.test import TestCase

from enterprise_data.admin_analytics.data_loaders import fetch_max_enrollment_datetime


class TestDataLoaders(TestCase):
    """
    Test suite for the utility functions in the admin_analytics package for data loading operations.
    """

    def test_fetch_max_enrollment_datetime(self):
        """
        Validate the fetch_max_enrollment_datetime function.
        """
        with patch(
            'enterprise_data.admin_analytics.data_loaders.EnterpriseLearnerEnrollment.objects.aggregate'
        ) as mock_aggregate:
            mock_aggregate.return_value = {'max_created': datetime(2024, 7, 26, 21, 38, 48, 298000)}

            max_enrollment_date = fetch_max_enrollment_datetime()
            self.assertEqual(max_enrollment_date.strftime('%Y-%m-%d'), '2024-07-26')

            # Validate the case where the query returns an empty result.
            mock_aggregate.return_value = {'max_created': None}
            max_enrollment_date = fetch_max_enrollment_datetime()
            self.assertIsNone(max_enrollment_date)
