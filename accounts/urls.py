from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import LoginForm

app_name = "accounts"

FORM_PAGE = "accounts/form_page.html"
MESSAGE_PAGE = "accounts/message.html"

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(
        authentication_form=LoginForm, template_name=FORM_PAGE,
        extra_context={"title": "Log in", "submit_label": "Log in"}, redirect_authenticated_user=True,
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("profile/", views.profile, name="profile"),
    path("password/", views.password_change, name="password_change"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/new/", views.address_form, name="address_create"),
    path("addresses/<int:pk>/edit/", views.address_form, name="address_edit"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("addresses/<int:pk>/default/", views.address_default, name="address_default"),
    path("orders/", views.order_list, name="orders"),
    path("orders/<str:number>/invoice.pdf", views.order_invoice, name="order_invoice"),
    path("orders/<str:number>/", views.order_detail, name="order_detail"),
    path("orders/<str:number>/cancel/", views.order_cancel, name="order_cancel"),
    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name=FORM_PAGE, email_template_name="registration/password_reset_email.html",
        subject_template_name="registration/password_reset_subject.txt",
        success_url=reverse_lazy("accounts:password_reset_done"),
        extra_context={"title": "Reset password", "submit_label": "Send reset link",
                       "intro": "Enter the email address on your account. Accounts registered with only a mobile number cannot use email reset; contact the store for help."},
    ), name="password_reset"),
    path("password-reset/sent/", auth_views.PasswordResetDoneView.as_view(
        template_name=MESSAGE_PAGE,
        extra_context={"title": "Check your email", "message": "If an account exists for that email, a reset link has been sent. The link expires after a short time."},
    ), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name=FORM_PAGE, success_url=reverse_lazy("accounts:password_reset_complete"),
        extra_context={"title": "Choose a new password", "submit_label": "Set new password"},
    ), name="password_reset_confirm"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(
        template_name=MESSAGE_PAGE,
        extra_context={"title": "Password updated", "message": "Your password has been reset. You can now log in.",
                       "action_url": reverse_lazy("accounts:login"), "action_label": "Log in"},
    ), name="password_reset_complete"),
]
