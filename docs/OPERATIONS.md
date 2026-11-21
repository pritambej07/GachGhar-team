# Operations guide

## Creating staff roles
Staff access uses Django's built-in groups and permissions. Create these groups in Admin > Groups and tick the matching permissions:
- Product Manager: store | product, product variant, product image, category (add, change).
- Inventory Manager: store | stock movement (add, view), product variant (view).
- Order Manager: store | order (view, change), order event (view).
- Customer Support: accounts | user (view), store | order (view), review (view).
- Finance: store | order (view), store | stock movement (view).
- Read-only Staff: all `view` permissions.

Give the owner the superuser account. Every admin change is recorded in Django's admin history (the "History" button on each record).

## Order lifecycle
Placed > Confirmed > Shipped > Delivered. Cancellation is allowed from Placed or Confirmed and returns the stock to inventory automatically. Use the validated admin actions on the order list. Shipment statuses cannot move backwards, and cancelled orders cannot receive shipments.

## Cash on delivery
Enable it in Site settings. Mark a COD payment as Paid in admin after collecting the money. Razorpay orders cannot be manually marked paid or refunded from admin.

## Razorpay
Razorpay checkout and signed webhooks are implemented. Configure `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in the private environment. Configure the provider's webhook URL to the application's Razorpay webhook endpoint and select `payment.captured` and `refund.processed` events. Never mark a payment paid from the browser redirect.

Only a signed, processed Razorpay refund event can move a Razorpay order to Refunded; processed partial refunds are recorded in the order timeline and do not mark the full order refunded until the cumulative confirmed amount reaches the order total. The admin does not initiate or confirm refunds. Initiate the refund in Razorpay and let its webhook update the order.

## Rate-limit cache
Local development uses in-process memory. For multiple production workers, configure Django's database cache with `DJANGO_CACHE_BACKEND=django.core.cache.backends.db.DatabaseCache` and `DJANGO_CACHE_LOCATION=django_cache`, then run `python manage.py createcachetable`. Use the same shared backend for every web worker.

## Backup and restore
SQLite: copy `db.sqlite3` and the `media/` folder while the server is stopped. PostgreSQL: use `pg_dump` and `pg_restore`. Test a restore on a separate machine before relying on it.

## Safe integration smoke tests

### Real Gmail SMTP delivery

Use a Gmail account you control, enable 2-Step Verification, and create a Gmail App Password. Do not use your normal Google password, paste credentials into chat, or commit them. In a fresh PowerShell window, enter the App Password through the secure credential prompt; these settings apply only to that PowerShell process and its child processes:

```powershell
$gmail = Get-Credential -UserName 'your-address@gmail.com' -Message 'Enter a Gmail App Password'
$env:EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
$env:EMAIL_HOST = 'smtp.gmail.com'
$env:EMAIL_PORT = '587'
$env:EMAIL_HOST_USER = $gmail.UserName
$env:EMAIL_HOST_PASSWORD = $gmail.GetNetworkCredential().Password.Replace(' ', '')
$env:EMAIL_USE_TLS = 'True'
$env:DEFAULT_FROM_EMAIL = $gmail.UserName
```

Send one message to a mailbox you control:

```powershell
python manage.py shell -c "from django.conf import settings; from django.core.mail import send_mail; print(send_mail('GachGhar SMTP smoke test', 'If you received this, SMTP accepted the message.', settings.DEFAULT_FROM_EMAIL, ['your-address@gmail.com'], fail_silently=False))"
```

The command should print `1`. Confirm delivery in Inbox or Spam; SMTP acceptance alone does not prove inbox placement. To exercise a password-reset email, use a dedicated test account and a mailbox you control. Do not trigger tests against customers' addresses. Close the PowerShell window when finished; do not copy these values into `.env` unless you intentionally choose to configure local SMTP.

### Razorpay test-mode checkout

1. In the Razorpay Dashboard, explicitly switch to **Test Mode** and create test API keys. Use only `rzp_test_...` credentials and a separate webhook secret; never use live keys or real payment instruments for this test.
2. Use an isolated local/staging database and a test customer. For a fresh, disposable SQLite database, prepare one in a PowerShell process with:

   ```powershell
   $testDb = (Join-Path $env:TEMP 'gachghar-razorpay-test.sqlite3').Replace('\', '/')
   $env:DATABASE_URL = "sqlite:///$testDb"
   python manage.py migrate
   python manage.py createsuperuser
   ```

   Sign in to Admin on that isolated instance and create a test category, a clearly labeled test-only product/variant, and a stock movement to add test stock. Do not use production customer data or point test keys at the production database.
3. In the same PowerShell process, enter the Test Mode values without placing secrets in command history:

   ```powershell
   $env:RAZORPAY_KEY_ID = Read-Host 'Razorpay Test Key ID'
   $secureSecret = Read-Host 'Razorpay Test Key Secret' -AsSecureString
   $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureSecret)
   try { $env:RAZORPAY_KEY_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
   finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
   $secureWebhook = Read-Host 'Razorpay Test Webhook Secret' -AsSecureString
   $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureWebhook)
   try { $env:RAZORPAY_WEBHOOK_SECRET = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
   finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
   $env:EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
   ```

   Keep secrets in environment variables or a secret manager, not in source files or `.env` for this temporary test.
4. Start `python manage.py runserver 127.0.0.1:8000`, sign in as the test customer, add the test product, and proceed to checkout. Complete one payment using a test card/UPI method from Razorpay's current official Test Mode documentation. Confirm the order total, payment status, order confirmation and retry behavior. Repeat with an official failure test instrument; the order must not become Paid.
5. To verify webhooks, configure a webhook in the **Test Mode** dashboard for an already-approved, reachable HTTPS test/staging URL ending in `/payment/webhook/razorpay/`, select `payment.captured` and `refund.processed`, and use that webhook's test secret as `RAZORPAY_WEBHOOK_SECRET`. Verify deliveries and responses in the dashboard. Do not expose a local development server through a tunnel or point test webhooks at production. If no approved HTTPS test endpoint exists, keep webhook verification to the automated signed-webhook tests.
6. After testing, stop the test server, close the PowerShell window, and verify that no test order or test keys were placed in the production environment. The isolated test database is separate from `db.sqlite3`; do not run migrations against the production database for this exercise.

Razorpay's test instruments can change; use the current official test details in its dashboard/documentation rather than real card or bank credentials.
