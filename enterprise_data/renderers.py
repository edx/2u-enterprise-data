"""
Renderers for enterprise data views.
"""

from rest_framework_csv.renderers import CSVStreamingRenderer


class EnrollmentsCSVRenderer(CSVStreamingRenderer):
    """
    Custom streaming csv renderer for EnterpriseLearnerEnrollment data.
    """

    # This will be used as CSV header for csv generated from `admin-portal`.
    # Do not change the order of fields below. Ordering is important because csv generated
    # on `admin-portal` should match `progress_v3` csv generated in `enterprise_reporting`
    # Order and field names below should match with `EnterpriseLearnerEnrollmentSerializer.fields`
    header = [
        'enrollment_id', 'enterprise_enrollment_id', 'is_consent_granted', 'paid_by',
        'user_current_enrollment_mode', 'enrollment_date', 'unenrollment_date',
        'unenrollment_end_within_date', 'is_refunded', 'seat_delivery_method',
        'offer_id', 'offer_name', 'offer_type', 'coupon_code', 'coupon_name', 'contract_id',
        'course_list_price', 'amount_learner_paid', 'course_key', 'courserun_key',
        'course_title', 'course_pacing_type', 'course_start_date', 'course_end_date',
        'course_duration_weeks', 'course_max_effort', 'course_min_effort',
        'course_primary_program', 'primary_program_type', 'course_primary_subject', 'has_passed',
        'last_activity_date', 'progress_status', 'passed_date', 'current_grade',
        'letter_grade', 'enterprise_user_id', 'user_email', 'user_account_creation_date',
        'user_country_code', 'user_username', 'user_first_name', 'user_last_name', 'enterprise_name',
        'enterprise_customer_uuid', 'enterprise_sso_uid', 'created', 'course_api_url', 'total_learning_time_hours',
        'is_subsidy', 'course_product_line', 'budget_id', 'enterprise_flex_group_name', 'enterprise_flex_group_uuid',
        'course_progress',
        'course_passing_grade',
    ]


class IndividualEnrollmentsCSVRenderer(CSVStreamingRenderer):
    """
    Custom streaming csv renderer for advance analytics individual enrollments data.
    """

    header = [
        'email',
        'course_title',
        'course_subject',
        'enroll_type',
        'enterprise_enrollment_date',
    ]


class IndividualCompletionsCSVRenderer(CSVStreamingRenderer):
    """
    Custom streaming csv renderer for advance analytics individual completions data.
    """

    header = [
        'email',
        'course_title',
        'course_subject',
        'enroll_type',
        'passed_date',
    ]


class IndividualEngagementsCSVRenderer(CSVStreamingRenderer):
    """
    Custom streaming csv renderer for advance analytics individual engagements data.
    """

    header = [
        'email',
        'course_title',
        'course_subject',
        'enroll_type',
        'activity_date',
        'learning_time_hours',
        'is_engaged_video',
        'is_engaged_forum',
        'is_engaged_problem',
    ]


class ExecEdLCModulePerformanceCSVRenderer(CSVStreamingRenderer):
    """
    Custom streaming csv renderer for EnterpriseExecEdLCModulePerformance data.
    """

    # This will be used as CSV header for csv generated from `admin-portal`.
    # Do not change the order of fields below without updating the requested column order (ENT-12312).
    # Order and field names below should match with `EnterpriseExecEdLCModulePerformanceSerializer.fields`
    header = [
        'ocm_lms_user_id', 'first_name', 'last_name', 'username', 'status', 'last_access',
        'presentation_name', 'presentation_abbreviation', 'module_number', 'module_name',
        'orientation_module_accessed', 'hours_online', 'final_mark', 'assign_grade',
        'extensions_requested', 'pass_grade', 'module_grade', 'last_module_release_date',
        'last_module_end_date', 'all_activities_completed_count', 'all_activities_total_count',
        'graded_activities_completed_count', 'graded_activities_total_count',
        'assessment_activities_completed_count', 'assessment_activities_total_count',
        'course_material_activities_completed_count', 'course_material_activities_total_count',
        'discussion_forum_activities_completed_count', 'discussion_forum_activities_total_count',
        'percentage_completed_activities', 'percentage_completed_graded_activities',
        'avg_after_lo_score', 'avg_before_lo_score', 'avg_lo_percentage_difference', 'company_name',
        'course_abbreviation', 'course_abbreviation_short', 'course_code', 'course_name',
        'course_type', 'department', 'enrolment_id', 'enterprise_customer_uuid', 'faculty',
        'is_internal_subsidy', 'log_viewed', 'module_1_release_date', 'module_performance_unique_id',
        'ocm_courserun_key', 'ocm_enrollment_id', 'olc_user_id', 'partner_short_name',
        'presentation_close_date', 'presentation_code', 'presentation_start_date',
        'product_life_cycle_status', 'product_type', 'promotion_category_name', 'promotion_code',
        'question_name', 'registration_id', 'school', 'subject_vertical', 'subsidy_transaction_id',
        'university_abbreviation', 'university_country', 'university_name',
    ]


class LeaderboardCSVRenderer(CSVStreamingRenderer):
    """
    Custom streaming csv renderer for advance analytics leaderboard data.
    """

    header = [
        'email',
        'learning_time_hours',
        'session_count',
        'average_session_length',
        'course_completion_count',
    ]
