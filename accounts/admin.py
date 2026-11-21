from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Address, Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class AddressInline(admin.TabularInline):
    model = Address
    extra = 0
    fields = ("full_name", "phone", "line1", "line2", "city", "state", "pincode", "address_type", "is_default")


admin.site.unregister(User)


@admin.register(User)
class CustomerAdmin(UserAdmin):
    inlines = [ProfileInline, AddressInline]
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name", "profile__phone")
    list_filter = ("is_staff", "is_active")
