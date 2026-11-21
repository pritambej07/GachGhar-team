# GachGhar — Final QA ও Release Checklist

এই Patch-এ Product Review-এর Star UI, PDF Invoice, Admin Order List উন্নতি, Delivery Rule consistency এবং Security defaults যোগ/সংশোধন করা হয়েছে। Browser-এ প্রকৃত visual পরীক্ষা এবং live hosting পরীক্ষা স্থানীয় Project-এ চালাতে হবে; এগুলো এই build environment থেকে করা সম্ভব হয়নি।

## 1. Install-এর পর automated checks

PowerShell (Project root, virtual environment active):

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py test accounts store --verbosity 1
python manage.py check --deploy
```

`check --deploy`-এর ফল production domain/HTTPS/hosting configuration অনুযায়ী পর্যালোচনা করতে হবে। HTTPS live না হওয়া পর্যন্ত HSTS চালু করবেন না। `DEBUG=False`, strong `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, HTTPS, secure cookies এবং HSTS hosting-এর `.env`-এ ঠিকভাবে সেট করতে হবে। Secret কখনো Git বা ZIP-এ রাখবেন না।

## 2. Product review ও stars

- Customer login করে Product Detail-এ গিয়ে 1–5 star বেছে Review submit করবে।
- নতুন Review Admin approval না হওয়া পর্যন্ত public হবে না।
- Admin > Store > Reviews থেকে Approve/Reject করুন।
- Approved Review Product page-এ stars, average rating এবং review count দেখাবে।
- একই customer একই Product-এ একটি Review create/update করতে পারবে। Update করলে moderation আবার pending হবে।

## 3. Invoice PDF

- Customer > My Orders > Order Detail খুলুন।
- `Download invoice PDF` চাপুন।
- PDF-এ Order number/date, delivery address, item/SKU/quantity, subtotal, coupon discount, delivery charge এবং grand total মিলিয়ে দেখুন।
- অন্য Customer-এর Order number দিয়ে Invoice URL খুললে access পাওয়া যাবে না।

## 4. Delivery charge policy

- Admin > Store > Site Settings-এ `Shipping fee` এবং `Free shipping threshold` নির্ধারণ করুন।
- Threshold ফাঁকা রাখলে Free Shipping বন্ধ থাকবে।
- Threshold-এর সমান বা বেশি merchandise subtotal হলে shipping শূন্য হবে।
- Coupon discount free-shipping eligibility কমাবে না; checkout preview ও saved Order একই charge দেখাবে।
- আপনার ব্যবসার প্রকৃত delivery rates/area policy Admin-এ বসানোর আগে মালিকের অনুমোদন নিন। Patch কোনো অনুমানভিত্তিক টাকা নির্ধারণ করে না।

## 5. Admin Order Management

- Admin > Store > Orders-এ search, status/payment/method filters এবং date hierarchy ব্যবহার করুন।
- Status পরিবর্তনের জন্য built-in validated actions ব্যবহার করুন; Order record সরাসরি edit/delete করা বন্ধ রাখা হয়েছে।
- COD payment সংগ্রহের পর Admin থেকে Paid করা যাবে। Razorpay order Admin থেকে Paid/Refunded করা যাবে না; signed payment/refund webhook-ই status নিশ্চিত করে। Razorpay dashboard-এ refund শুরু করুন; `refund.processed` webhook সম্পূর্ণ refund নিশ্চিত না করা পর্যন্ত order Refunded হবে না।

## 6. Visual ও responsive manual test

Browser zoom 100% রেখে নিচের viewport-এ Home, Product Listing, Product Detail, Cart, Checkout, My Orders, Order Detail এবং Admin-এর গুরুত্বপূর্ণ পেজ পরীক্ষা করুন:

| Device viewport | কী দেখবেন |
|---|---|
| 360 × 800 | কোনো horizontal page overflow নেই; buttons readable/tappable |
| 390 × 844 | Product image, variants, stars, review form ঠিক আছে |
| 768 × 1024 | Tablet layout, navigation ও checkout columns ঠিক আছে |
| 1024 × 768 | Desktop/tablet transition ঠিক আছে |
| 1440 × 900 | Content অতিরিক্ত চওড়া নয়; cards ও whitespace ঠিক আছে |

বিশেষ করে keyboard focus, form validation, image loading, menu open/close, table horizontal scrolling এবং checkout summary পরীক্ষা করুন।

## 7. Final live checks

- Real Gmail test email-এর জন্য নিজের ঠিকানা ব্যবহার করুন; `YOUR_EMAIL@gmail.com` placeholder নয়।
- Test order দিয়ে Order, Payment, Shipping, Refund Email বাস্তবে পৌঁছায় কি না যাচাই করুন।
- Razorpay test mode-এ payment success/failure/webhook পরীক্ষা করুন; production credentials কখনো test report-এ রাখবেন না।
- Backup নিন, তারপর HTTPS domain-এ deploy করুন। Live deployment এই patch-এর অংশ নয়।
