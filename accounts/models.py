from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models, transaction

PIN_VALIDATOR = RegexValidator(r"^\d{6}$", "Enter a valid 6-digit PIN code.")


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    phone = models.CharField(max_length=10, unique=True, null=True, blank=True)

    def __str__(self):
        return self.user.email or self.phone or f"User {self.user_id}"


class Address(models.Model):
    ADDRESS_TYPE_CHOICES = [
        ('home', 'Home'),
        ('office', 'Office'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=10)
    line1 = models.CharField("address line 1", max_length=200)
    line2 = models.CharField("apartment / landmark", max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField("PIN code", max_length=6, validators=[PIN_VALIDATOR])
    country = models.CharField(max_length=60, default="India", editable=False)
    address_type = models.CharField("address type", max_length=10, choices=ADDRESS_TYPE_CHOICES, default='home')
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-id"]
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.full_name}, {self.city} {self.pincode}"

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default:
                Address.objects.filter(user=self.user, is_default=True).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)

    def snapshot(self):
        """Plain-dict copy stored on orders so later address edits do not change history."""
        return {
            "full_name": self.full_name, "phone": self.phone, "line1": self.line1, "line2": self.line2,
            "city": self.city, "state": self.state, "pincode": self.pincode, "country": self.country,
        }
