from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import Profile
from .utils import normalize_phone

User = get_user_model()


class EmailOrPhoneBackend(ModelBackend):
    """Authenticate with an email address or an Indian mobile number plus password."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get(User.USERNAME_FIELD) or "").strip()
        user = self._find_user(identifier)
        if user is None:
            User().set_password(password or "")  # equalise timing with the success path
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def _find_user(self, identifier):
        if "@" in identifier:
            return User.objects.filter(email__iexact=identifier).order_by("id").first()
        phone = normalize_phone(identifier)
        if not phone:
            return None
        profile = Profile.objects.select_related("user").filter(phone=phone).first()
        return profile.user if profile else None
