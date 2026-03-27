"""Tests for JobAlertDetector."""
import pytest

from backend.app.services.job_alert_detector import JobAlertDetector


@pytest.fixture
def detector() -> JobAlertDetector:
    return JobAlertDetector()


class TestSenderDomainDetection:
    def test_linkedin_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="New jobs for you",
            sender_email="jobs-noreply@linkedin.com",
        )

    def test_indeed_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Weekly digest",
            sender_email="alert@indeed.com",
        )

    def test_glassdoor_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="3 new jobs matching Python Engineer",
            sender_email="noreply@glassdoor.com",
        )

    def test_naukri_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Jobs for you",
            sender_email="donotreply@naukri.com",
        )

    def test_unknown_domain_not_job_alert(self, detector: JobAlertDetector) -> None:
        assert not detector.is_job_alert(
            subject="Hello",
            sender_email="someone@gmail.com",
        )

    def test_domain_check_is_case_insensitive(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Hello",
            sender_email="alert@LinkedIn.com",
        )


class TestSubjectKeywordDetection:
    def test_job_alert_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Your job alert: Python Engineer",
            sender_email="no-reply@randomcompany.com",
        )

    def test_new_jobs_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="5 new jobs matching your profile",
            sender_email="digest@somesite.com",
        )

    def test_job_opportunity_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Exciting job opportunity at Acme Corp",
            sender_email="recruiter@headhunter.io",
        )

    def test_hiring_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="We are hiring! Senior Python Developer",
            sender_email="hr@startup.com",
        )

    def test_jobs_for_you_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Jobs for you this week",
            sender_email="digest@jobboard.com",
        )

    def test_unrelated_subject_not_job_alert(self, detector: JobAlertDetector) -> None:
        assert not detector.is_job_alert(
            subject="Your invoice is ready",
            sender_email="billing@acme.com",
        )

    def test_subject_check_is_case_insensitive(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="JOB ALERT: Senior Engineer",
            sender_email="hr@company.com",
        )


class TestSnippetDetection:
    def test_snippet_with_job_keyword(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Weekly digest",
            sender_email="digest@somesite.com",
            snippet="We found 3 new jobs matching your search for Python Developer.",
        )

    def test_empty_snippet_not_matched(self, detector: JobAlertDetector) -> None:
        assert not detector.is_job_alert(
            subject="Hello there",
            sender_email="friend@example.com",
            snippet="",
        )

    def test_none_snippet_handled(self, detector: JobAlertDetector) -> None:
        # Should not raise
        result = detector.is_job_alert(
            subject="Meeting tomorrow",
            sender_email="boss@work.com",
            snippet=None,
        )
        assert result is False
