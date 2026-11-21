import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify



def validate_image_size(file):
    if file.size > 5 * 1024 * 1024:
        raise ValidationError("Image must be 5 MB or smaller.")


IMAGE_VALIDATORS = [FileExtensionValidator(["jpg", "jpeg", "png", "webp"]), validate_image_size]


def unique_slug(model, base, instance_pk=None):
    slug = slugify(base)[:80] or uuid.uuid4().hex[:8]
    candidate, n = slug, 2
    while model.objects.filter(slug=candidate).exclude(pk=instance_pk).exists():
        candidate = f"{slug}-{n}"
        n += 1
    return candidate


class SiteSettings(models.Model):
    """Single-row store configuration managed from the admin (CMS-style)."""

    logo = models.ImageField("logo override", upload_to="cms/branding/", blank=True, validators=IMAGE_VALIDATORS,
                             help_text="Leave blank to use the official supplied GachGhar logo.")
    announcement_text = models.CharField(max_length=200, blank=True)
    announcement_active = models.BooleanField(default=False)
    hero_heading = models.CharField(max_length=120, blank=True)
    hero_description = models.TextField(blank=True)
    hero_button_text = models.CharField(max_length=40, default="Shop plants")
    hero_image = models.ImageField(upload_to="cms/hero/", blank=True, validators=IMAGE_VALIDATORS)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_address = models.TextField(blank=True)
    footer_text = models.TextField(blank=True)
    cod_enabled = models.BooleanField("cash on delivery enabled", default=False)
    shipping_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"),
                                       validators=[MinValueValidator(Decimal("0"))],
                                       help_text="Flat shipping fee in INR. This is charged below the free-shipping threshold.")
    free_shipping_threshold = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                                  validators=[MinValueValidator(Decimal("0"))],
                                                  help_text="Cart merchandise subtotal (before coupon discount) at or above this amount gets free shipping. Leave blank to disable free shipping.")

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Category(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, related_name="children", on_delete=models.PROTECT,
                               help_text="Leave blank for a top-level category.")
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, validators=IMAGE_VALIDATORS)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"
        indexes = [models.Index(fields=["is_active", "parent"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Category, self.name, self.pk)
        super().save(*args, **kwargs)

    def clean(self):
        node = self.parent
        seen = set()
        while node is not None:
            node_id = node.pk if node.pk is not None else id(node)
            if self.pk is not None and node_id == self.pk:
                raise ValidationError({"parent": "A category cannot be its own ancestor."})
            if node_id in seen:
                raise ValidationError({"parent": "The category hierarchy cannot contain a cycle."})
            seen.add(node_id)
            node = node.parent

    def get_absolute_url(self):
        return reverse("store:category", args=[self.slug])

    def descendant_ids(self):
        ids, frontier, seen = [self.pk], [self.pk], {self.pk}
        while frontier:
            frontier = list(
                Category.objects.filter(parent_id__in=frontier)
                .exclude(pk__in=seen)
                .values_list("pk", flat=True)
            )
            seen.update(frontier)
            ids.extend(frontier)
        return ids


class Product(models.Model):
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    description = models.TextField(blank=True)
    highlights = models.TextField(blank=True, help_text="One highlight per line.")
    specifications = models.TextField(blank=True, help_text="One 'Label: value' per line.")
    care_instructions = models.TextField(blank=True)
    is_active = models.BooleanField("visible on store", default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["is_active", "is_featured"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Product, self.name, self.pk)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:product", args=[self.slug])

    def highlight_lines(self):
        return [line.strip() for line in self.highlights.splitlines() if line.strip()]

    def specification_rows(self):
        rows = []
        for line in self.specifications.splitlines():
            if ":" in line:
                label, value = line.split(":", 1)
                rows.append((label.strip(), value.strip()))
        return rows


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", validators=IMAGE_VALIDATORS)
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"Image for {self.product}"


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=120, default="Standard", help_text="e.g. 6-inch pot, 500 g pack")
    sku = models.CharField("SKU", max_length=64, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    compare_at_price = models.DecimalField("original price", max_digits=10, decimal_places=2, null=True, blank=True,
                                           help_text="Shown as a strike-through only when higher than the price.")
    stock = models.PositiveIntegerField(default=0, editable=False,
                                        help_text="Changed only through stock movements.")
    low_stock_threshold = models.PositiveIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "price", "id"]
        indexes = [
            models.Index(fields=["is_active", "stock"]),
            models.Index(fields=["product", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(price__gte=0), name="variant_price_non_negative"),
            models.CheckConstraint(condition=models.Q(stock__gte=0), name="variant_stock_non_negative"),
        ]

    def __str__(self):
        return f"{self.product.name} ({self.name})"

    def clean(self):
        if self.compare_at_price is not None and self.price is not None and self.compare_at_price < self.price:
            raise ValidationError({"compare_at_price": "The original price must be higher than the selling price."})

    @property
    def discount_percent(self):
        if self.compare_at_price and self.compare_at_price > self.price:
            return round((self.compare_at_price - self.price) / self.compare_at_price * 100)
        return 0

    @property
    def is_low_stock(self):
        return 0 < self.stock <= self.low_stock_threshold


class StockMovement(models.Model):
    """Immutable inventory ledger. Stock on a variant is only changed by creating a movement."""

    class Reason(models.TextChoices):
        RESTOCK = "restock", "Restock"
        ADJUSTMENT = "adjustment", "Manual adjustment"
        SALE = "sale", "Sale"
        CANCELLATION = "cancellation", "Cancelled order returned to stock"

    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="stock_movements")
    change = models.IntegerField(help_text="Positive adds stock, negative removes stock.")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.CharField(max_length=200, blank=True)
    order = models.ForeignKey("Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_movements")
    balance_after = models.PositiveIntegerField(editable=False, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.variant} {self.change:+d}"

    def clean(self):
        if self.pk:
            return
        if self.change == 0:
            raise ValidationError({"change": "The change cannot be zero."})
        if self.variant_id and self.variant.stock + self.change < 0:
            raise ValidationError({"change": f"Only {self.variant.stock} units are in stock."})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Stock movements are permanent records and cannot be edited.")
        with transaction.atomic():
            variant = ProductVariant.objects.select_for_update().get(pk=self.variant_id)
            new_stock = variant.stock + self.change
            if new_stock < 0:
                raise ValidationError(f"Insufficient stock for {variant.sku}: {variant.stock} available.")
            variant.stock = new_stock
            ProductVariant.objects.filter(pk=variant.pk).update(stock=new_stock)
            self.balance_after = new_stock
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock movements cannot be deleted.")


class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False, help_text="Only approved reviews are shown publicly.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "is_approved"]),
            models.Index(fields=["is_approved", "-created_at"]),
        ]
        constraints = [models.UniqueConstraint(fields=["product", "user"], name="one_review_per_customer")]

    def __str__(self):
        return f"{self.rating}/5 for {self.product}"


class Guide(models.Model):
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(help_text="Plain text. Blank lines start new paragraphs.")
    is_published = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Guide, self.title, self.pk)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:guide", args=[self.slug])


class StaticPage(models.Model):
    """Editable informational pages: about, contact, privacy, terms, shipping, returns."""

    slug = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True, help_text="Plain text. Blank lines start new paragraphs.")
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("store:page", args=[self.slug])


class HomeSection(models.Model):
    class Kind(models.TextChoices):
        FEATURED = "featured", "Featured products"
        CATEGORIES = "categories", "Shop by category"
        CATEGORY_PRODUCTS = "category_products", "Products from one category"
        GUIDES = "guides", "Plant care guides"
        REVIEWS = "reviews", "Approved customer reviews"
        NEWSLETTER = "newsletter", "Newsletter signup"

    title = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL,
                                 help_text="Required for 'Products from one category'.")
    enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title or self.get_kind_display()

    def clean(self):
        if self.kind == self.Kind.CATEGORY_PRODUCTS and not self.category_id:
            raise ValidationError({"category": "Choose a category for this section."})


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email


class Cart(models.Model):
    """One cart per authenticated user, or one guest cart identified by a session token."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                                related_name="cart")
    guest_token = models.CharField(max_length=64, null=True, blank=True, unique=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(user__isnull=False) | models.Q(guest_token__isnull=False),
                                   name="cart_has_owner"),
        ]


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveSmallIntegerField(default=1,
                                                validators=[MinValueValidator(1), MaxValueValidator(20)])

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["cart", "variant"], name="one_line_per_variant"),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name="cart_quantity_positive"),
        ]


class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="wishlisted_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="one_wishlist_entry")]


class Order(models.Model):
    class Status(models.TextChoices):
        PLACED = "placed", "Placed"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"

    number = models.CharField(max_length=24, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="orders")
    idempotency_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLACED, db_index=True)
    payment_method = models.CharField(max_length=20, default="cod")
    razorpay_order_id = models.CharField(max_length=100, blank=True, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    payment_verified_at = models.DateTimeField(null=True, blank=True)

    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    discount_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    coupon_code = models.CharField(max_length=40, blank=True)
    shipping_fee = models.DecimalField(max_digits=8, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["number"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["payment_status", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f"GG{timezone.now():%Y%m%d}{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    @property
    def can_cancel(self):
        return (
            self.status in (self.Status.PLACED, self.Status.CONFIRMED)
            and self.payment_status != self.PaymentStatus.PAID
        )

    def get_absolute_url(self):
        return reverse("accounts:order_detail", args=[self.number])


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=160)
    variant_name = models.CharField(max_length=120)
    sku = models.CharField(max_length=64)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]


class OrderEvent(models.Model):
    """Append-only order history. Events cannot be edited or deleted."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(max_length=20)
    note = models.CharField(max_length=240, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Order events are permanent and cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Order events cannot be deleted.")


class AssistantActionLog(models.Model):
    """Audit trail of data-changing actions requested through the AI Gardener. Read-only in admin."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name="assistant_actions")
    tool = models.CharField(max_length=40)
    succeeded = models.BooleanField(default=False)
    summary = models.CharField(max_length=300, blank=True, help_text="Tool arguments only. No personal data.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tool} ({'ok' if self.succeeded else 'rejected'})"


class Coupon(models.Model):
    """Simple discount code. Validated and applied on the server at checkout only."""

    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage off"
        FIXED = "fixed", "Fixed amount off"

    code = models.CharField(max_length=40, unique=True, help_text="Stored in capitals. Customers can type any case.")
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))],
                                help_text="Percent (1-100) or rupees, depending on type.")
    min_order_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"),
                                          help_text="Minimum cart subtotal (before discount) needed.")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Total uses allowed. Blank = unlimited.")
    is_active = models.BooleanField(default=True)
    categories = models.ManyToManyField(Category, blank=True, related_name="coupons",
                                        help_text="Optional. If set, only these categories (and sub-categories) get the discount.")
    products = models.ManyToManyField(Product, blank=True, related_name="coupons",
                                      help_text="Optional. If set, only these products get the discount.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "code"]),
            models.Index(fields=["starts_at", "ends_at"]),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        if self.discount_type == self.DiscountType.PERCENT and self.value is not None and self.value > 100:
            raise ValidationError({"value": "A percentage cannot be more than 100."})
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End must be after the start."})

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def times_used(self):
        return self.redemptions.exclude(order__status="cancelled").count()


class CouponRedemption(models.Model):
    """One row per order that used a coupon. Cancelled orders stop counting toward the usage limit."""

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name="redemptions")
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="coupon_redemption")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class Shipment(models.Model):
    """Manual carrier tracking details maintained by store staff."""

    class Status(models.TextChoices):
        LABEL_CREATED = "label_created", "Label created"
        PICKED_UP = "picked_up", "Picked up"
        IN_TRANSIT = "in_transit", "In transit"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        DELIVERED = "delivered", "Delivered"
        EXCEPTION = "exception", "Delivery exception"

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipment")
    carrier = models.CharField(max_length=80, blank=True)
    tracking_number = models.CharField(max_length=120, blank=True)
    tracking_url = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.LABEL_CREATED)
    estimated_delivery = models.DateField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "-updated_at"]),
        ]

    STATUS_RANK = {
        Status.LABEL_CREATED: 0,
        Status.PICKED_UP: 1,
        Status.IN_TRANSIT: 2,
        Status.OUT_FOR_DELIVERY: 3,
        Status.DELIVERED: 4,
    }

    def __str__(self):
        return f"Shipment for {self.order.number}"

    def clean(self):
        if self.order_id and self.order.status == Order.Status.CANCELLED:
            raise ValidationError({"order": "A shipment cannot be created or updated for a cancelled order."})

        if self.pk:
            previous_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous_status and previous_status != self.status:
                is_terminal = previous_status == self.Status.DELIVERED
                is_exception = self.status == self.Status.EXCEPTION
                is_recovery = previous_status == self.Status.EXCEPTION and self.status in {
                    self.Status.PICKED_UP,
                    self.Status.IN_TRANSIT,
                    self.Status.OUT_FOR_DELIVERY,
                    self.Status.DELIVERED,
                }
                is_backward = (
                    self.status == self.Status.LABEL_CREATED
                    or previous_status in self.STATUS_RANK
                    and self.status in self.STATUS_RANK
                    and self.STATUS_RANK[self.status] < self.STATUS_RANK[previous_status]
                )
                if is_terminal or (is_backward and not is_exception and not is_recovery):
                    raise ValidationError({"status": "Shipment status cannot move backwards."})

        moving_statuses = {
            self.Status.PICKED_UP,
            self.Status.IN_TRANSIT,
            self.Status.OUT_FOR_DELIVERY,
            self.Status.DELIVERED,
        }
        if self.order_id and self.status in moving_statuses:
            order = self.order
            if (
                order.payment_method == "razorpay"
                and order.payment_status != Order.PaymentStatus.PAID
            ):
                raise ValidationError({"status": "Verify the online payment before shipping this order."})

    def save(self, *args, **kwargs):
        if self.status in {
            self.Status.PICKED_UP, self.Status.IN_TRANSIT,
            self.Status.OUT_FOR_DELIVERY, self.Status.DELIVERED,
        } and not self.shipped_at:
            self.shipped_at = timezone.now()
        if self.status == self.Status.DELIVERED and not self.delivered_at:
            self.delivered_at = timezone.now()
        super().save(*args, **kwargs)


class RazorpayWebhookEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    processed = models.BooleanField(default=False)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["processed", "received_at"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self):
        return self.event_type + " - " + self.event_id
