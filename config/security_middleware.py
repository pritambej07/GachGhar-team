"""Security middleware for GachGhar.

Adds Content-Security-Policy and other defense-in-depth headers.
CSP is configured to allow self-hosted assets plus trusted third-party
services (Google Fonts, Razorpay checkout). Adjust for your deployment.
"""

from django.conf import settings


class SecurityHeadersMiddleware:
    """Add security headers to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content-Security-Policy
        # - default-src 'self'
        # - style-src: self + Google Fonts (inline styles from Django templates are avoided)
        # - font-src: Google Fonts
        # - script-src: self + Razorpay checkout + inline scripts (needed for Razorpay handler)
        # - img-src: self + data: (for product images)
        # - connect-src: self + Razorpay API
        # - frame-src: Razorpay Standard Checkout's hosted payment frame
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' https://checkout.razorpay.com https://api.razorpay.com 'unsafe-inline'",
            "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https:",
            "connect-src 'self' https://api.razorpay.com",
            "frame-src https://checkout.razorpay.com https://api.razorpay.com",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]
        if not settings.DEBUG:
            # Upgrade insecure requests only when not in debug (local HTTP)
            csp_directives.append("upgrade-insecure-requests")

        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # Additional hardening headers (some already set in settings via middleware,
        # but we reinforce them here for clarity and defense in depth)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "unsafe-none")

        return response
