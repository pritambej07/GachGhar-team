# Shipping tracking and customer emails

## Shipment workflow

1. Open Django Admin → Shipments → Add shipment.
2. Select the order and enter carrier, tracking number, optional carrier tracking URL, and estimated delivery date.
3. Save the shipment. Signed-in customers can see these details on Account → My Orders → View order. Guest customers can see tracking from their order-confirmation page in the same recent-order browser session.
4. Update the shipment status as the carrier progresses:
   - Label created
   - Picked up
   - In transit
   - Out for delivery
   - Delivered
   - Delivery exception

Shipment status changes are monotonic: they may skip intermediate carrier milestones, but cannot move backwards after delivery or return to an earlier milestone. A shipment cannot be added to a cancelled order.

Carrier milestones can arrive before staff confirmation: a placed order advances through Confirmed to Shipped when shipment progress is recorded. When a shipped order's shipment moves to Delivered, its order status moves to Delivered. The order timeline records these changes.

This is a **manual tracking integration**: staff enter carrier tracking details in Admin. Live carrier scans and automatic label booking are not enabled because no Shiprocket or other carrier API credentials were supplied.

## Customer email notifications

The application sends best-effort emails for:
- Order placed
- Order confirmed
- Order shipped
- Order delivered
- Order cancelled
- Payment verified
- Full Razorpay refund confirmed by webhook
- Shipment tracking updates

Email is sent to the email address saved on the order. If no email address exists, the notification is skipped. Email server failures do not block checkout or order updates.

Configure SMTP in the private `.env` file. Example variable names are already documented in `.env.example`:
`EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`.

Never commit or upload `.env`.
