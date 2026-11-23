
from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from . import services
from .models import (
    AssistantActionLog,
    Cart,
    Category,
    Coupon,
    CouponRedemption,
    Guide,
    HomeSection,
    NewsletterSubscriber,
    Order,
    OrderEvent,
    OrderItem,
    Product,
    ProductImage,
    ProductVariant,
    Review,
    SiteSettings,
    Shipment,
    StaticPage,
    StockMovement,
)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fieldsets = (
        ("Branding", {
            "fields": (
                "logo",
                "hero_image",
                "hero_heading",
                "hero_description",
                "hero_button_text",
            )
        }),
        ("Announcement", {
            "fields": ("announcement_text", "announcement_active")
        }),
        ("Contact and footer", {
            "fields": (
                "contact_email",
                "contact_phone",
                "contact_address",
                "footer_text",
            )
        }),
        ("Legal and grievance disclosures", {
            "fields": (
                "legal_entity_name",
                "grievance_officer_name",
                "grievance_email",
                "grievance_phone",
                "grievance_hours",
            ),
            "description": "Enter only verified owner details. These values appear on the Contact page.",
        }),
        ("Checkout and shipping", {
            "fields": (
                "cod_enabled",
                "shipping_fee",
                "free_shipping_threshold",
            )
        }),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "parent")
    search_fields = ("name", "description")
    exclude = ("slug",)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "sort_order")
    verbose_name = "product image upload"
    verbose_name_plural = "product image uploads (stored in configured media storage)"


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = (
        "name",
        "sku",
        "price",
        "compare_at_price",
        "stock",
        "low_stock_threshold",
        "is_active",
        "sort_order",
    )
    readonly_fields = ("stock",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "is_active",
        "is_featured",
        "updated_at",
    )
    list_filter = ("is_active", "is_featured", "category")
    list_editable = ("is_active", "is_featured")
    search_fields = ("name", "description")
    exclude = ("slug",)
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "variant",
        "change",
        "reason",
        "balance_after",
        "created_by",
        "created_at",
    )
    list_filter = ("reason",)
    search_fields = ("variant__sku", "variant__product__name", "note")
    readonly_fields = (
        "balance_after",
        "created_by",
        "created_at",
        "order",
    )
    fields = (
        "variant",
        "change",
        "reason",
        "note",
        "balance_after",
        "created_by",
        "created_at",
        "order",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [
                f.name
                for f in self.model._meta.fields
                if f.name != "id"
            ]
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        try:
            super().save_model(request, obj, form, change)
        except ValidationError as error:
            self.message_user(
                request,
                " ".join(error.messages),
                level=messages.ERROR,
            )

    def has_change_permission(self, request, obj=None):
        return (
            obj is None
            and super().has_change_permission(request)
        )

    def has_delete_permission(self, request, obj=None):
        return False


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    can_delete = False
    readonly_fields = (
        "status",
        "note",
        "actor",
        "created_at",
    )
    fields = (
        "status",
        "note",
        "actor",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


def _transition_action(new_status, label):
    def action(modeladmin, request, queryset):
        done = 0

        for order in queryset:
            try:
                services.transition_order(
                    order,
                    new_status,
                    actor=request.user,
                    note=f"{label} by staff.",
                )
                done += 1

            except ValidationError as error:
                modeladmin.message_user(
                    request,
                    f"{order.number}: {' '.join(error.messages)}",
                    level=messages.ERROR,
                )

        if done:
            modeladmin.message_user(
                request,
                f"{done} order(s) marked {label.lower()}.",
            )

    action.__name__ = f"mark_{str(new_status).lower()}"
    action.short_description = label

    return action


def _payment_action(payment_status, label):
    def action(modeladmin, request, queryset):
        done = 0
        for order in queryset:
            try:
                services.record_payment(
                    order,
                    payment_status,
                    actor=request.user,
                )
                done += 1
            except ValidationError as error:
                modeladmin.message_user(
                    request,
                    f"{order.number}: {' '.join(error.messages)}",
                    level=messages.ERROR,
                )

        if done:
            modeladmin.message_user(request, f"{done} order(s) payment set to {label}.")

    action.__name__ = f"mark_payment_{str(payment_status).lower()}"
    action.short_description = f"Payment: mark {label}"

    return action


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "email",
        "phone",
        "status",
        "payment_status",
        "payment_method",
        "shipment_status",
        "shipping_fee",
        "total",
        "created_at",
    )
    list_filter = (
        "status",
        "payment_status",
        "payment_method",
    )
    search_fields = (
        "number",
        "email",
        "phone",
        "user__email",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 30
    list_select_related = ("user",)
    show_full_result_count = False
    inlines = [OrderItemInline, OrderEventInline]

    actions = [
        _transition_action(
            Order.Status.CONFIRMED,
            "Confirmed",
        ),
        _transition_action(
            Order.Status.SHIPPED,
            "Shipped",
        ),
        _transition_action(
            Order.Status.DELIVERED,
            "Delivered",
        ),
        _transition_action(
            Order.Status.CANCELLED,
            "Cancelled",
        ),
        _payment_action(
            Order.PaymentStatus.PAID,
            "paid",
        ),
    ]

    @admin.display(description="Shipment")
    def shipment_status(self, obj):
        try:
            return obj.shipment.get_status_display()
        except Shipment.DoesNotExist:
            return "—"

    def get_readonly_fields(self, request, obj=None):
        return [
            f.name
            for f in self.model._meta.fields
            if f.name != "id"
        ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "rating",
        "is_approved",
        "created_at",
    )
    list_filter = ("is_approved", "rating")
    search_fields = ("product__name", "user__email", "title", "body")
    list_select_related = ("product", "user")
    list_per_page = 40
    actions = ["approve", "reject"]

    @admin.action(description="Approve selected reviews")
    def approve(self, request, queryset):
        queryset.update(is_approved=True)

    @admin.action(description="Reject selected reviews")
    def reject(self, request, queryset):
        queryset.update(is_approved=False)


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "is_published",
        "sort_order",
    )
    list_editable = ("is_published", "sort_order")
    exclude = ("slug",)


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "slug",
        "is_published",
        "updated_at",
    )
    list_editable = ("is_published",)


@admin.register(HomeSection)
class HomeSectionAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "kind",
        "category",
        "enabled",
        "sort_order",
    )
    list_editable = ("enabled", "sort_order")


@admin.register(NewsletterSubscriber)
class NewsletterAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at")
    search_fields = ("email",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "updated_at")
    readonly_fields = (
        "user",
        "guest_token",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(AssistantActionLog)
class AssistantActionLogAdmin(admin.ModelAdmin):
    """Read-only audit trail of AI Gardener actions."""

    list_display = (
        "created_at",
        "tool",
        "succeeded",
        "user",
    )
    list_filter = ("tool", "succeeded")
    readonly_fields = (
        "user",
        "tool",
        "succeeded",
        "summary",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CouponRedemptionInline(admin.TabularInline):
    model = CouponRedemption
    extra = 0
    can_delete = False
    readonly_fields = (
        "order",
        "user",
        "discount_amount",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "discount_type",
        "value",
        "min_order_value",
        "starts_at",
        "ends_at",
        "usage_limit",
        "times_used",
        "is_active",
    )
    list_filter = ("is_active", "discount_type")
    search_fields = ("code", "description")
    filter_horizontal = ("categories", "products")
    inlines = [CouponRedemptionInline]



@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "carrier", "tracking_number", "status", "estimated_delivery", "updated_at")
    list_filter = ("status", "carrier")
    search_fields = ("order__number", "order__email", "tracking_number", "order__phone")
    raw_id_fields = ("order",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Order", {"fields": ("order",)}),
        ("Carrier tracking", {"fields": ("carrier", "tracking_number", "tracking_url", "status", "estimated_delivery")}),
        ("Timestamps", {"fields": ("shipped_at", "delivered_at", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        previous = Shipment.objects.filter(pk=obj.pk).first() if change else None
        super().save_model(request, obj, form, change)
        changed = previous is None or any(
            getattr(previous, field) != getattr(obj, field)
            for field in ("carrier", "tracking_number", "tracking_url", "status", "estimated_delivery")
        )
        if changed and (obj.tracking_number or obj.tracking_url or obj.status != Shipment.Status.LABEL_CREATED):
            services.record_shipment_update(obj, actor=request.user, created=previous is None)
