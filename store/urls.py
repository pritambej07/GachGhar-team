from django.urls import path

from . import commerce, views

app_name = "store"

from . import payment_views

urlpatterns = [
    path('payment/verify/', payment_views.verify_payment, name='verify_payment'),
    path('payment/webhook/razorpay/', payment_views.razorpay_webhook, name='razorpay_webhook'),
    path("", views.home, name="home"),
    path("products/", views.products, name="products"),
    path("category/<slug:slug>/", views.category_detail, name="category"),
    path("product/<slug:slug>/", views.product_detail, name="product"),
    path("product/<slug:slug>/review/", views.review_submit, name="review_submit"),
    path("search/", views.search, name="search"),
    path("search/suggestions/", views.search_suggestions, name="search_suggestions"),
    path("cart/", commerce.cart_page, name="cart"),
    path("cart/api/", commerce.cart_api, name="cart_api"),
    path("cart/add/", commerce.cart_add, name="cart_add"),
    path("cart/update/<int:item_id>/", commerce.cart_update, name="cart_update"),
    path("wishlist/", commerce.wishlist_page, name="wishlist"),
    path("wishlist/toggle/<int:product_id>/", commerce.wishlist_toggle, name="wishlist_toggle"),
    path("wishlist/to-cart/<int:product_id>/", commerce.wishlist_to_cart, name="wishlist_to_cart"),
    path("order/<str:number>/payment/", commerce.payment_page, name="payment_page"),
    path("checkout/", commerce.checkout, name="checkout"),
    path("checkout/coupon/apply/", commerce.coupon_apply, name="coupon_apply"),
    path("checkout/coupon/remove/", commerce.coupon_remove, name="coupon_remove"),
    path("order/<str:number>/thank-you/", commerce.order_success, name="order_success"),
    path("guides/", views.guides, name="guides"),
    path("guides/<slug:slug>/", views.guide_detail, name="guide"),
    path("blog/", views.blog, name="blog"),
    path("blog/<slug:slug>/", views.blog_detail, name="blog_detail"),
    path("pages/<slug:slug>/", views.page, name="page"),
    path("newsletter/", views.newsletter_subscribe, name="newsletter"),
    path("assistant/", views.assistant_page, name="assistant"),
    path("assistant/api/", views.assistant_api, name="assistant_api"),
    path("assistant/confirm/", views.assistant_confirm, name="assistant_confirm"),
    path("assistant/history/", views.assistant_history, name="assistant_history"),
    path("assistant/clear/", views.assistant_clear, name="assistant_clear"),
    path("robots.txt", views.robots_txt, name="robots"),
]
