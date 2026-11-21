import hashlib

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.conf import settings
from django.contrib.auth.password_validation import validate_password

from .models import Address, Profile
from .utils import normalize_phone

User = get_user_model()
LOGIN_WINDOW_SECONDS = 15 * 60


class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=120, label="Full name")
    contact = forms.CharField(max_length=254, label="Email or phone number",
                              help_text="Use an email address or a 10-digit Indian mobile number. You need only one.")
    password = forms.CharField(label="Password", widget=forms.PasswordInput(render_value=False))
    confirm_password = forms.CharField(label="Confirm password", widget=forms.PasswordInput(render_value=False))
    accept_terms = forms.BooleanField(label="I agree to the Terms and Conditions and Privacy Policy",
                                      error_messages={"required": "Please accept the terms to continue."})

    def clean_contact(self):
        raw = self.cleaned_data["contact"].strip()
        if "@" in raw:
            try:
                validate_email(raw)
            except ValidationError:
                raise forms.ValidationError("Enter a valid email address.")
            email = raw.lower()
            if User.objects.filter(email__iexact=email).exists():
                raise forms.ValidationError("An account with this email already exists.")
            self.contact_fields = {"email": email, "phone": None}
        else:
            phone = normalize_phone(raw)
            if not phone:
                raise forms.ValidationError("Enter a valid 10-digit mobile number, or use an email address.")
            if Profile.objects.filter(phone=phone).exists():
                raise forms.ValidationError("An account with this phone number already exists.")
            self.contact_fields = {"email": "", "phone": phone}
        return raw

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password and password != cleaned.get("confirm_password"):
            self.add_error("confirm_password", "Passwords do not match.")
        if password:
            try:
                validate_password(password)
            except ValidationError as error:
                self.add_error("password", error)
        return cleaned


class LoginForm(AuthenticationForm):
    """Login form with a simple per-identifier failure throttle."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email or phone number"

    def _throttle_key(self):
        identifier = (self.data.get("username") or "").strip().lower()
        remote_addr = self.request.META.get("REMOTE_ADDR", "") if self.request else ""
        key = hashlib.sha256(f"{identifier}\0{remote_addr}".encode()).hexdigest()
        return "login-fail:" + key

    def clean(self):
        key = self._throttle_key()
        if cache.get(key, 0) >= settings.LOGIN_MAX_FAILURES:
            raise ValidationError("Too many failed attempts. Please try again in 15 minutes.")
        try:
            cleaned = super().clean()
        except ValidationError:
            cache.add(key, 0, LOGIN_WINDOW_SECONDS)
            cache.incr(key)
            raise
        cache.delete(key)
        return cleaned


class ProfileForm(forms.ModelForm):
    phone = forms.CharField(required=False, max_length=15, label="Mobile number")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["phone"].initial = profile.phone if profile else ""

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email is already used by another account.")
        return email

    def clean_phone(self):
        raw = self.cleaned_data.get("phone", "").strip()
        if not raw:
            return ""
        phone = normalize_phone(raw)
        if not phone:
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        if Profile.objects.filter(phone=phone).exclude(user=self.instance).exists():
            raise forms.ValidationError("This mobile number is already used by another account.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("phone"):
            raise forms.ValidationError("Keep at least an email address or a mobile number on your account.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=commit)
        Profile.objects.update_or_create(user=user, defaults={"phone": self.cleaned_data["phone"] or None})
        return user


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["full_name", "phone", "line1", "line2", "city", "state", "pincode", "address_type", "is_default"]
        labels = {"is_default": "Use as my default address", "line2": "Apartment / landmark (optional)"}

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone:
            raise forms.ValidationError("Enter a valid 10-digit mobile number.")
        return phone

    def clean_address_type(self):
        address_type = self.cleaned_data.get("address_type", "home")
        valid_types = [t[0] for t in Address.ADDRESS_TYPE_CHOICES]
        if address_type not in valid_types:
            raise forms.ValidationError("Invalid address type.")
        return address_type


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(label="Current password", widget=forms.PasswordInput(render_value=False))
    new_password = forms.CharField(label="New password", widget=forms.PasswordInput(render_value=False))
    confirm_password = forms.CharField(label="Confirm new password", widget=forms.PasswordInput(render_value=False))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current_password(self):
        current = self.cleaned_data.get("current_password")
        if current and not self.user.check_password(current):
            raise forms.ValidationError("Your current password is incorrect.")
        return current

    def clean(self):
        cleaned = super().clean()
        new = cleaned.get("new_password")
        confirm = cleaned.get("confirm_password")

        if new and confirm and new != confirm:
            self.add_error("confirm_password", "New passwords do not match.")

        if new:
            try:
                validate_password(new, self.user)
            except ValidationError as error:
                self.add_error("new_password", error)
        return cleaned
