from smtplib import SMTPException
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Profile
from .utils import normalize_phone

User = get_user_model()
PASSWORD = "Str0ng-pass-123"


class PhoneNormalisationTests(TestCase):
    def test_accepts_common_indian_formats(self):
        self.assertEqual(normalize_phone("98765 43210"), "9876543210")
        self.assertEqual(normalize_phone("+91 98765-43210"), "9876543210")

    def test_rejects_invalid_numbers(self):
        self.assertIsNone(normalize_phone("12345"))
        self.assertIsNone(normalize_phone("1234567890"))
        self.assertIsNone(normalize_phone("abc 9876543210 xyz"))
        self.assertIsNone(normalize_phone("++91 98765-43210"))


class RegistrationTests(TestCase):
    def register(self, contact, **overrides):
        data = {"full_name": "Asha Roy", "contact": contact, "password": PASSWORD,
                "confirm_password": PASSWORD, "accept_terms": "on"}
        data.update(overrides)
        return self.client.post(reverse("accounts:register"), data)

    def test_register_with_email_needs_no_otp(self):
        response = self.register("asha@example.com")
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertTrue(User.objects.filter(email="asha@example.com").exists())

    def test_register_with_phone_and_login_by_phone(self):
        self.register("9876543210")
        self.client.logout()
        self.assertTrue(self.client.login(username="9876543210", password=PASSWORD))
        self.assertEqual(Profile.objects.get().phone, "9876543210")

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(username="x", email="dup@example.com", password=PASSWORD)
        response = self.register("dup@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="dup@example.com").count(), 1)

    def test_password_mismatch_is_rejected(self):
        response = self.register("new@example.com", confirm_password="Different-pass-999")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_welcome_email_failure_is_logged_without_blocking_registration(self):
        with mock.patch("accounts.views.send_mail", side_effect=SMTPException("SMTP unavailable")):
            with self.assertLogs("accounts.views", level="ERROR") as log:
                response = self.register("welcome@example.com")

        self.assertRedirects(response, reverse("accounts:dashboard"))
        user = User.objects.get(email="welcome@example.com")
        self.assertIn(str(user.pk), log.output[0])

    def test_unexpected_mail_backend_failure_does_not_break_registration(self):
        with mock.patch("accounts.views.send_mail", side_effect=RuntimeError("mail backend unavailable")):
            with self.assertLogs("accounts.views", level="ERROR"):
                response = self.register("welcome-runtime@example.com")

        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.assertTrue(User.objects.filter(email="welcome-runtime@example.com").exists())


class LoginTests(TestCase):
    def test_login_with_email(self):
        User.objects.create_user(username="u1", email="login@example.com", password=PASSWORD)
        response = self.client.post(reverse("accounts:login"), {"username": "login@example.com", "password": PASSWORD})
        self.assertRedirects(response, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_wrong_password_does_not_log_in(self):
        User.objects.create_user(username="u2", email="bad@example.com", password=PASSWORD)
        self.client.post(reverse("accounts:login"), {"username": "bad@example.com", "password": "wrong"})
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(LOGIN_MAX_FAILURES=1)
    def test_failed_attempt_throttle_is_scoped_to_client_ip(self):
        User.objects.create_user(username="u3", email="throttle@example.com", password=PASSWORD)
        url = reverse("accounts:login")
        data = {"username": "throttle@example.com", "password": "wrong"}

        self.client.post(url, data, REMOTE_ADDR="192.0.2.1")
        response = self.client.post(url, data, REMOTE_ADDR="192.0.2.2")
        same_ip_response = self.client.post(url, data, REMOTE_ADDR="192.0.2.1")

        self.assertNotContains(response, "Too many failed attempts")
        self.assertContains(same_ip_response, "Too many failed attempts")
