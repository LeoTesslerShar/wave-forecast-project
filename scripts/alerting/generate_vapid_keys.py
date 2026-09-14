"""Generates a real VAPID keypair for Web Push (prompts/phase-4-alerting.md section 5).

Prints the values to paste into .env -- never writes them to a file, never commits them
(hard rule 4). Round-trips through pywebpush's own Vapid.from_string on the private key
before printing, so a key this script produces is guaranteed to actually load.

Usage:
    py -3.13 scripts/alerting/generate_vapid_keys.py
"""
import base64

from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_numbers = private_key.private_numbers()
    public_numbers = private_numbers.public_numbers

    private_raw = private_numbers.private_value.to_bytes(32, "big")
    # Uncompressed EC point: 0x04 || X (32 bytes) || Y (32 bytes) -- the format browsers'
    # Push API expects for applicationServerKey.
    public_raw = (
        b"\x04"
        + public_numbers.x.to_bytes(32, "big")
        + public_numbers.y.to_bytes(32, "big")
    )

    private_b64 = _b64url(private_raw)
    public_b64 = _b64url(public_raw)

    # Prove it actually loads the way app/alerting/push.py will load it, before printing
    # anything -- a key that LOOKS right but doesn't parse is worse than no key.
    Vapid02.from_string(private_key=private_b64)

    print("Verified round-trip OK. Add these to .env (never commit real values):\n")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("VAPID_CLAIMS_EMAIL=<a real contact address -- push services may use it>")
    print(
        "\nThe frontend's Push subscription call (browser-side, not built in Phase 5 -- "
        "the form only POSTs an already-obtained subscription to /push-subscriptions) "
        "would use VAPID_PUBLIC_KEY as its applicationServerKey."
    )


if __name__ == "__main__":
    main()
