"""
Utility functions for fetching data from the database.
"""
from datetime import timezone
from logging import getLogger

from django.db.models import Max
from django.utils.timezone import is_naive, make_aware

from enterprise_data.models import EnterpriseLearnerEnrollment

LOGGER = getLogger(__name__)


def fetch_max_enrollment_datetime():
    """
    Fetch the latest created date from the enterprise_learner_enrollment table.

    created will be same for all records as this is added at the time of data load. Which is when the async process
    populates the data in the table. We can use this to get the latest data load time.
    """
    result = EnterpriseLearnerEnrollment.objects.aggregate(max_created=Max('created'))
    max_created = result.get('max_created')
    if not max_created:
        return None
    if is_naive(max_created):
        max_created = make_aware(max_created)
    return max_created.astimezone(timezone.utc)
