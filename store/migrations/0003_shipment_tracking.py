# Generated for GachGhar shipment tracking.
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0002_razorpaywebhookevent_order_payment_verified_at_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="Shipment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("carrier", models.CharField(blank=True, max_length=80)),
                ("tracking_number", models.CharField(blank=True, max_length=120)),
                ("tracking_url", models.URLField(blank=True, max_length=500)),
                ("status", models.CharField(
                    choices=[
                        ("label_created", "Label created"),
                        ("picked_up", "Picked up"),
                        ("in_transit", "In transit"),
                        ("out_for_delivery", "Out for delivery"),
                        ("delivered", "Delivered"),
                        ("exception", "Delivery exception"),
                    ],
                    default="label_created",
                    max_length=24,
                )),
                ("estimated_delivery", models.DateField(blank=True, null=True)),
                ("shipped_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="shipment",
                    to="store.order",
                )),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]
