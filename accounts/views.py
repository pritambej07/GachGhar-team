
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from store.models import Order, WishlistItem
from store.services import cart_item_count, transition_order

from .forms import AddressForm, PasswordChangeForm, ProfileForm, RegisterForm
from .models import Address, Profile
from django.contrib.auth import update_session_auth_hash

User = get_user_model()
AUTH_BACKEND = "accounts.backends.EmailOrPhoneBackend"
logger = logging.getLogger(__name__)


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        fields = form.contact_fields

        with transaction.atomic():
            user = User.objects.create_user(
                username=uuid.uuid4().hex,
                email=fields["email"],
                password=data["password"],
                first_name=data["full_name"][:150],
            )
            Profile.objects.create(user=user, phone=fields["phone"])

        if fields["email"]:
            subject = "Welcome to GachGhar – Happy to Have You!"

            message = f"""Hello {data['full_name']},

A warm welcome to GachGhar!

We are delighted to have you as a member of the GachGhar family.

Thank you for creating your account with us.

GachGhar is here to help you bring more greenery, freshness, and happiness into your life.

Your account has been successfully created, and you can now explore our website and enjoy your shopping experience.

We truly appreciate your trust in us.

If you ever need help, our team will be happy to assist you.

Thank you for choosing GachGhar!

With love and green wishes,

GachGhar Team
gachghar2026@gmail.com

Grow Green. Live Green. Stay Happy!
"""

            try:
                send_mail(
                    subject,
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [fields["email"]],
                    fail_silently=False,
                )
            except Exception:
                logger.exception("Could not send welcome email for user %s", user.pk)

        login(request, user, backend=AUTH_BACKEND)
        messages.success(request, "Welcome to GachGhar. Your account is ready.")
        return redirect("accounts:dashboard")

    return render(
        request,
        "accounts/form_page.html",
        {
            "form": form,
            "title": "Create account",
            "submit_label": "Create account",
        },
    )


@login_required
def dashboard(request):
    return render(request, "accounts/dashboard.html", {
        "recent_orders": Order.objects.filter(user=request.user)[:3],
        "default_address": request.user.addresses.filter(is_default=True).first(),
        "wishlist_count": WishlistItem.objects.filter(user=request.user).count(),
        "cart_count": cart_item_count(request),
    })


@login_required
def profile(request):
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=request.user, profile=profile_obj)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
        return redirect("accounts:profile")

    return render(request, "accounts/form_page.html", {
        "form": form,
        "title": "Edit profile",
        "submit_label": "Save changes",
    })


@login_required
def password_change(request):
    """Custom password change view that requires current password verification."""
    form = PasswordChangeForm(request.POST or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        user = request.user
        user.set_password(form.cleaned_data["new_password"])
        user.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password has been updated. You are still logged in.")
        return redirect("accounts:profile")

    return render(request, "accounts/form_page.html", {
        "form": form,
        "title": "Change password",
        "submit_label": "Update password",
    })


@login_required
def address_list(request):
    return render(request, "accounts/addresses.html", {
        "addresses": request.user.addresses.all()
    })


@login_required
def address_form(request, pk=None):
    instance = get_object_or_404(Address, pk=pk, user=request.user) if pk else None
    form = AddressForm(request.POST or None, instance=instance)

    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, "Address saved.")
        return redirect("accounts:addresses")

    title = "Edit address" if instance else "Add address"

    return render(request, "accounts/form_page.html", {
        "form": form,
        "title": title,
        "submit_label": "Save address",
    })


@login_required
@require_POST
def address_delete(request, pk):
    get_object_or_404(Address, pk=pk, user=request.user).delete()
    messages.success(request, "Address removed.")
    return redirect("accounts:addresses")


@login_required
@require_POST
def address_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save()
    messages.success(request, "Default address updated.")
    return redirect("accounts:addresses")


@login_required
@never_cache
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "accounts/orders.html", {"orders": orders})


@login_required
@never_cache
def order_detail(request, number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "events").select_related("shipment"),
        number=number,
        user=request.user,
    )
    return render(request, "accounts/order_detail.html", {"order": order})


@login_required
@require_POST
def order_cancel(request, number):
    order = get_object_or_404(Order, number=number, user=request.user)

    try:
        transition_order(
            order,
            Order.Status.CANCELLED,
            actor=request.user,
            note="Cancelled by customer.",
        )
        messages.success(request, "Your order has been cancelled.")
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))

    return redirect("accounts:order_detail", number=order.number)


@never_cache
def order_invoice(request, number):
    """Build a PDF invoice for the signed-in owner or the guest session that placed it."""
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    is_owner = request.user.is_authenticated and order.user_id == request.user.pk
    is_guest_owner = number in request.session.get("recent_orders", [])
    if not (is_owner or is_guest_owner):
        raise Http404

    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    invoice_font = "GachGharInvoice"
    invoice_font_path = settings.BASE_DIR / "static" / "fonts" / "NotoSansBengali-wght.ttf"
    if invoice_font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(invoice_font, str(invoice_font_path), shapable=True))

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title=f"GachGhar Invoice {order.number}",
        author="GachGhar",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="InvoiceTitle", parent=styles["Title"], fontName=invoice_font))
    styles.add(ParagraphStyle(name="InvoiceHeading1", parent=styles["Heading1"], fontName=invoice_font))
    styles.add(ParagraphStyle(name="InvoiceHeading2", parent=styles["Heading2"], fontName=invoice_font))
    styles.add(ParagraphStyle(name="InvoiceNormal", parent=styles["Normal"], fontName=invoice_font))
    styles.add(ParagraphStyle(name="InvoiceRight", parent=styles["Normal"], alignment=TA_RIGHT,
                              fontName=invoice_font))
    styles.add(ParagraphStyle(name="InvoiceSmall", parent=styles["Normal"], fontName=invoice_font,
                              fontSize=8, leading=11))
    story = [
        Paragraph("GachGhar", styles["InvoiceTitle"]),
        Paragraph("INVOICE", styles["InvoiceHeading1"]),
        Paragraph(f"Invoice / Order No: {escape(order.number)}", styles["InvoiceNormal"]),
        Paragraph(f"Order date: {order.created_at:%d %b %Y, %I:%M %p}", styles["InvoiceNormal"]),
        Spacer(1, 8 * mm),
        Paragraph("Bill to", styles["InvoiceHeading2"]),
    ]
    address = order.shipping_address or {}
    address_lines = [address.get("full_name", "Customer"), address.get("line1", ""),
                     address.get("line2", ""),
                     ", ".join(x for x in [address.get("city", ""), address.get("state", "")] if x),
                     address.get("pincode", ""), f"Phone: {order.phone}"]
    story.append(Paragraph(
        "<br/>".join(escape(str(line)) for line in address_lines if line),
        styles["InvoiceNormal"],
    ))
    story.append(Spacer(1, 7 * mm))

    rows = [["Product", "SKU", "Qty", "Unit price (INR)", "Amount (INR)"]]
    for item in order.items.all():
        rows.append([
            Paragraph(escape(f"{item.product_name} — {item.variant_name}"), styles["InvoiceSmall"]),
            Paragraph(escape(item.sku), styles["InvoiceSmall"]), str(item.quantity),
            f"{item.unit_price:.2f}", f"{item.line_total:.2f}",
        ])
    table = Table(rows, colWidths=[67 * mm, 27 * mm, 13 * mm, 34 * mm, 34 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f1e9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#173d2b")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5ce")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([table, Spacer(1, 6 * mm)])

    totals = [[Paragraph("Subtotal", styles["InvoiceNormal"]), f"INR {order.subtotal:.2f}"]]
    if order.discount_total:
        totals.append([
            Paragraph(escape(f"Discount ({order.coupon_code or 'Coupon'})"), styles["InvoiceNormal"]),
            f"- INR {order.discount_total:.2f}",
        ])
    totals.extend([
        [Paragraph("Delivery charge", styles["InvoiceNormal"]), f"INR {order.shipping_fee:.2f}"],
        [Paragraph("Grand total", styles["InvoiceNormal"]), f"INR {order.total:.2f}"],
    ])
    total_table = Table(totals, colWidths=[120 * mm, 55 * mm], hAlign="RIGHT")
    total_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#173d2b")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([total_table, Spacer(1, 12 * mm),
                  Paragraph("Thank you for shopping with GachGhar. Grow Green. Live Green.",
                            styles["InvoiceNormal"])])
    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="GachGhar-Invoice-{order.number}.pdf"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
