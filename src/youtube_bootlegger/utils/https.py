"""TLS trust for HTTPS requests, including standalone application builds."""

import ssl

import certifi


def create_https_context() -> ssl.SSLContext:
    """Use system/configured trust plus the application's bundled public roots.

    Frozen Python may retain build-machine OpenSSL certificate paths, notably
    on macOS. Shipping certifi alone doesn't make urllib use those roots.
    Keep default verification and any system/SSL_CERT_FILE roots, then add
    the portable bundle explicitly rather than changing process-wide settings.
    """
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    context.set_alpn_protocols(['http/1.1'])
    return context
