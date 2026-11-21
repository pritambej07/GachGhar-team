from django import forms
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from accounts.utils import normalize_phone

PAYMENT_LABELS = {"cod": "Cash on delivery", "razorpay": "Pay online (Razorpay)"}


class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=120, label="Full name")
    email = forms.EmailField(required=False, label="Email (optional)")
    phone = forms.CharField(max_length=15, label="Mobile number", help_text="10-digit Indian mobile number.")
    line1 = forms.CharField(max_length=200, label="Address line 1")
    line2 = forms.CharField(max_length=200, required=False, label="Apartment / landmark")
    city = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100)
    pincode = forms.CharField(max_length=6, label="PIN code")
    payment_method = forms.ChoiceField(label="Payment method")

    def __init__(self, *args, payment_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = [(code, PAYMENT_LABELS.get(code, code)) for code in payment_choices]

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        if not phone:
            raise ValidationError("Enter a valid 10-digit mobile number.")
        return phone

    def clean_pincode(self):
        pincode = self.cleaned_data["pincode"].strip()
        if not (len(pincode) == 6 and pincode.isdigit()):
            raise ValidationError("Enter a valid 6-digit PIN code.")
        return pincode

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()
        if email:
            validate_email(email)
        return email


class ReviewForm(forms.Form):
    RATING_CHOICES = [(i, f"{i} star{'s' if i > 1 else ''}") for i in range(5, 0, -1)]
    rating = forms.TypedChoiceField(choices=RATING_CHOICES, coerce=int, widget=forms.RadioSelect, label="Your rating")
    title = forms.CharField(max_length=120, required=False, label="Title (optional)")
    body = forms.CharField(min_length=10, max_length=2000, widget=forms.Textarea(attrs={"rows": 4}),
                           label="Your review", help_text="At least 10 characters. Reviews appear after approval.")

    def clean_title(self):
        return self.cleaned_data.get("title", "").strip()

    def clean_body(self):
        return self.cleaned_data["body"].strip()
