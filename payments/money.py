"""
Conversion between stored amounts and payment-gateway amounts.

Everything persisted in this project - ``Product.selling_price``,
``CartItem.price``, ``Invoice.total_amount``, ``InvoiceItem.price`` - is in
*major* units (rupees, dollars). Both Stripe and Razorpay work exclusively in
*minor* units (paise, cents). Doing that conversion inline is what produced the
under-charging bug where ``int(Decimal("20.50"))`` was sent to Stripe as 20
paise, so it lives here and is used at every gateway boundary.
"""

from decimal import Decimal, ROUND_HALF_UP

# Currencies Stripe treats as zero-decimal: the amount is already the smallest
# unit and must not be multiplied. https://stripe.com/docs/currencies
ZERO_DECIMAL_CURRENCIES = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
    "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}


def _factor(currency):
    return 1 if str(currency or "").lower() in ZERO_DECIMAL_CURRENCIES else 100


def to_minor_units(amount, currency="INR"):
    """
    Major units -> integer minor units, for sending to a payment gateway.

    ``to_minor_units(Decimal("20.50"))`` -> ``2050``
    """
    amount = Decimal(str(amount or 0))
    minor = (amount * _factor(currency)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    return int(minor)


def from_minor_units(amount, currency="INR"):
    """
    Integer minor units from a gateway -> major units, for storing.

    ``from_minor_units(2050)`` -> ``Decimal("20.50")``
    """
    amount = Decimal(str(amount or 0))
    return (amount / _factor(currency)).quantize(Decimal("0.01"))
