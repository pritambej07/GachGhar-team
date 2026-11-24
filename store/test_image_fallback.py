from decimal import Decimal

from django.test import TestCase

from .models import Cart, CartItem, Category, Product, ProductImage, ProductVariant


class ProductImageFallbackTests(TestCase):
    def test_homepage_renders_branded_image_when_product_has_no_photo(self):
        category = Category.objects.create(name="Indoor", slug="indoor")
        product = Product.objects.create(name="Aloe Vera", slug="aloe-vera", category=category)
        ProductVariant.objects.create(product=product, name="Standard", sku="ALOE-1", price=Decimal("99.00"))

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "product-placeholder.svg")
        self.assertContains(response, "product-card__fallback")
        self.assertContains(response, product.name)

    def test_product_detail_has_a_fallback_for_a_broken_image_url(self):
        category = Category.objects.create(name="Indoor", slug="indoor")
        product = Product.objects.create(name="Aloe Vera", slug="aloe-vera", category=category)
        ProductVariant.objects.create(product=product, name="Standard", sku="ALOE-1", price=Decimal("99.00"))
        ProductImage.objects.create(product=product, image="products/missing-aloe.jpg")

        response = self.client.get(product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-image-fallback")
        self.assertContains(response, "data-image-fallback-placeholder")
        self.assertContains(response, "product-placeholder.svg")
        self.assertContains(response, "missing-aloe.jpg")

    def test_cart_page_has_a_fallback_for_a_broken_image_url(self):
        category = Category.objects.create(name="Indoor", slug="indoor")
        product = Product.objects.create(name="Aloe Vera", slug="aloe-vera", category=category)
        variant = ProductVariant.objects.create(
            product=product, name="Standard", sku="ALOE-1", price=Decimal("99.00")
        )
        ProductImage.objects.create(product=product, image="products/missing-aloe.jpg")
        session = self.client.session
        session["guest_cart_token"] = "image-fallback-test"
        session.save()
        cart = Cart.objects.create(guest_token="image-fallback-test")
        CartItem.objects.create(cart=cart, variant=variant)

        response = self.client.get("/cart/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-image-fallback")
        self.assertContains(response, "data-image-fallback-placeholder")
        self.assertContains(response, "product-placeholder.svg")
