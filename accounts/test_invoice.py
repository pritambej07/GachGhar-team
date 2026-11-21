import base64
import re
import zlib
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from reportlab.platypus import Paragraph, Table

from store.models import Order, OrderItem
from store.tests import make_product


class InvoicePDFTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="invoice-owner", email="invoice@example.com", password="Strong-pass-123"
        )
        self.other = get_user_model().objects.create_user(
            username="invoice-other", email="other@example.com", password="Strong-pass-123"
        )
        self.product, self.variant = make_product("Invoice Money Plant", price="249.00", stock=3)
        self.order = Order.objects.create(
            user=self.user, email=self.user.email, phone="9876543210",
            subtotal=Decimal("498.00"), discount_total=Decimal("10.00"), coupon_code="SAVE10",
            shipping_fee=Decimal("40.00"), total=Decimal("528.00"),
            shipping_address={"full_name": "Invoice Owner", "line1": "1 Green Road",
                              "city": "Kolkata", "state": "West Bengal", "pincode": "700001"},
        )
        OrderItem.objects.create(
            order=self.order, variant=self.variant, product_name=self.product.name,
            variant_name=self.variant.name, sku=self.variant.sku,
            unit_price=Decimal("249.00"), quantity=2, line_total=Decimal("498.00"),
        )
        self.url = reverse("accounts:order_invoice", args=[self.order.number])

    def test_owner_can_download_pdf_invoice(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(b"%PDF", response.content[:10])
        self.assertIn(self.order.number.encode(), response["Content-Disposition"].encode())
        self.assertIn("no-store", response["Cache-Control"])

    def test_owner_order_page_links_to_invoice(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:order_detail", args=[self.order.number]))
        self.assertContains(response, reverse("accounts:order_invoice", args=[self.order.number]))
        self.assertIn("no-store", response["Cache-Control"])

    def test_other_customer_cannot_download_invoice(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_guest_who_placed_order_can_download_invoice_from_same_session(self):
        session = self.client.session
        session["recent_orders"] = [self.order.number]
        session.save()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_guest_order_confirmation_links_to_invoice(self):
        session = self.client.session
        session["recent_orders"] = [self.order.number]
        session.save()
        response = self.client.get(reverse("store:order_success", args=[self.order.number]))
        self.assertContains(response, self.url)
        self.assertIn("no-store", response["Cache-Control"])

    def test_unrelated_guest_cannot_download_invoice(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_invoice_preserves_bengali_customer_and_product_text(self):
        self.client.force_login(self.user)
        customer_name = "\u0986\u09b6\u09be \u09b0\u09be\u09df"
        product_name = "\u09ae\u09be\u09a8\u09bf \u09aa\u09cd\u09b2\u09be\u09a8\u09cd\u099f"
        self.order.shipping_address["full_name"] = customer_name
        self.order.save(update_fields=["shipping_address"])
        item = self.order.items.get()
        item.product_name = product_name
        item.save(update_fields=["product_name"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        from reportlab.pdfbase import pdfmetrics
        self.assertTrue(pdfmetrics.getFont("GachGharInvoice").shapable)
        streams = []
        for match in re.finditer(rb"\nstream\r?\n", response.content):
            end = response.content.find(b"endstream", match.end())
            if end < 0:
                continue
            stream = response.content[match.end():end].strip()
            try:
                decoded = zlib.decompress(stream)
            except zlib.error:
                try:
                    decoded = zlib.decompress(base64.a85decode(stream[:-2]))
                except (ValueError, zlib.error):
                    continue
            if b"beginbfchar" in decoded:
                streams.append(decoded)

        self.assertTrue(streams)
        unicode_map = b"\n".join(streams)
        expected_codepoints = {
            ord(character)
            for text in (customer_name, product_name)
            for character in text
            if "\u0980" <= character <= "\u09ff"
        }
        mapped_codepoints = {
            int(codepoint, 16)
            for match in re.finditer(rb"<[0-9a-fA-F]+>\s*<([0-9a-fA-F]+)>", unicode_map)
            for codepoint in re.findall(rb"[0-9a-fA-F]{4}", match.group(1))
        }
        self.assertTrue(expected_codepoints.issubset(mapped_codepoints))

    def test_invoice_renders_order_snapshot_and_all_totals(self):
        self.client.force_login(self.user)
        paragraphs = []
        tables = []
        original_paragraph = Paragraph
        original_table = Table

        def capture_paragraph(text, *args, **kwargs):
            paragraphs.append(str(text))
            return original_paragraph(text, *args, **kwargs)

        def capture_table(data, *args, **kwargs):
            tables.append(data)
            return original_table(data, *args, **kwargs)

        with mock.patch("reportlab.platypus.Paragraph", side_effect=capture_paragraph):
            with mock.patch("reportlab.platypus.Table", side_effect=capture_table):
                response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"%PDF", response.content[:10])
        self.assertTrue(any(self.order.number in text for text in paragraphs))
        self.assertTrue(any("Invoice Owner" in text and "1 Green Road" in text for text in paragraphs))
        self.assertTrue(any(self.product.name in text and self.variant.name in text for text in paragraphs))
        self.assertEqual(tables[0][1][2:], ["2", "249.00", "498.00"])
        self.assertIn("Subtotal", paragraphs)
        self.assertIn("Discount (SAVE10)", paragraphs)
        self.assertIn("Delivery charge", paragraphs)
        self.assertIn("Grand total", paragraphs)
        totals = [cell for row in tables[1] for cell in row if isinstance(cell, str)]
        self.assertEqual(totals, ["INR 498.00", "- INR 10.00", "INR 40.00", "INR 528.00"])

