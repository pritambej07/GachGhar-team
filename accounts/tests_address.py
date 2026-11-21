"""Tests for address management and password change features."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Address

User = get_user_model()
PASSWORD = "Str0ng-pass-123"


class AddressManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="addressuser", email="addr@example.com", password=PASSWORD)
        self.client.force_login(self.user)

    def test_create_address(self):
        response = self.client.post(reverse("accounts:address_create"), {
            "full_name": "John Doe",
            "phone": "9876543210",
            "line1": "123 Main Street",
            "line2": "Apt 4",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "address_type": "home",
            "is_default": "on",
        })
        self.assertRedirects(response, reverse("accounts:addresses"))
        self.assertEqual(Address.objects.count(), 1)
        address = Address.objects.first()
        self.assertEqual(address.full_name, "John Doe")
        self.assertTrue(address.is_default)

    def test_multiple_addresses(self):
        Address.objects.create(user=self.user, full_name="John Doe", phone="9876543210",
                               line1="123 Main Street", city="Mumbai", state="Maharashtra", pincode="400001", is_default=True)
        self.client.post(reverse("accounts:address_create"), {
            "full_name": "Jane Doe",
            "phone": "9876543211",
            "line1": "456 Office Park",
            "city": "Bangalore",
            "state": "Karnataka",
            "pincode": "560001",
            "address_type": "office",
        })
        self.assertEqual(Address.objects.count(), 2)
        default = Address.objects.get(is_default=True)
        self.assertEqual(default.full_name, "John Doe")

    def test_make_address_default(self):
        addr1 = Address.objects.create(user=self.user, full_name="Home", phone="9876543210",
                                       line1="Street 1", city="City A", state="State A", pincode="111111", is_default=True)
        addr2 = Address.objects.create(user=self.user, full_name="Office", phone="9876543211",
                                       line1="Street 2", city="City B", state="State B", pincode="222222")
        
        self.client.post(reverse("accounts:address_default", args=[addr2.pk]))
        addr1.refresh_from_db()
        addr2.refresh_from_db()
        self.assertFalse(addr1.is_default)
        self.assertTrue(addr2.is_default)

    def test_delete_address(self):
        addr = Address.objects.create(user=self.user, full_name="To Delete", phone="9876543210",
                                      line1="Street", city="City", state="State", pincode="333333")
        self.client.post(reverse("accounts:address_delete", args=[addr.pk]))
        self.assertEqual(Address.objects.count(), 0)

    def test_cannot_access_other_users_address(self):
        other_user = User.objects.create_user(username="otheruser", email="other@example.com", password=PASSWORD)
        other_address = Address.objects.create(user=other_user, full_name="Other", phone="9876543210",
                                               line1="Other St", city="Other City", state="OS", pincode="111111")
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:address_edit", args=[other_address.pk]))
        self.assertEqual(response.status_code, 404)


class PasswordChangeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pwuser", email="pw@example.com", password=PASSWORD)
        self.client.force_login(self.user)

    def test_password_change_with_correct_current(self):
        response = self.client.post(reverse("accounts:password_change"), {
            "current_password": PASSWORD,
            "new_password": "NewStr0ng-pass-456",
            "confirm_password": "NewStr0ng-pass-456",
        })
        self.assertRedirects(response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStr0ng-pass-456"))
        # User should still be logged in
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_password_change_with_wrong_current(self):
        response = self.client.post(reverse("accounts:password_change"), {
            "current_password": "wrong-current-pass",
            "new_password": "NewStr0ng-pass-456",
            "confirm_password": "NewStr0ng-pass-456",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "current password is incorrect")

    def test_password_change_mismatch(self):
        response = self.client.post(reverse("accounts:password_change"), {
            "current_password": PASSWORD,
            "new_password": "NewStr0ng-pass-456",
            "confirm_password": "Different-pass-789",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "do not match")

    def test_weak_password_rejected(self):
        response = self.client.post(reverse("accounts:password_change"), {
            "current_password": PASSWORD,
            "new_password": "weak",
            "confirm_password": "weak",
        })
        self.assertEqual(response.status_code, 200)
