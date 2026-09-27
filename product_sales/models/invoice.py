from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .product import Product

import secrets
import uuid

INVOICE_NUMBER_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def build_invoice_number():
    """
    Collision-resistant invoice number that fits the 20-char column.

    A plain second-resolution timestamp (the previous ``INV-%Y%m%d%H%M%S``)
    collides as soon as two customers check out inside the same second, and the
    column is unique - which surfaced to the second customer as a failed
    checkout.
    """
    suffix = "".join(secrets.choice(INVOICE_NUMBER_ALPHABET) for _ in range(6))
    return f"INV-{timezone.now():%Y%m%d}-{suffix}"


class Invoice(models.Model):
    """
        An ONLINE order placed through the storefront.
    """

    ORDER_STATUS = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("packed", "Packed"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]
     
    PAYMENT_METHOD = [
        ("card", "Card"),
        ("upi", "UPI"),
        ("cod", "Cash on Delivery"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=20, unique=True)
    
    user = models.ForeignKey(
        "account.User",
        on_delete=models.CASCADE,
        related_name="invoices",
    )

    customer_id = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    shipping_address = models.TextField(blank=True, null=True)
    stripe_checkout_session_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
    )

    invoice_date = models.DateField(auto_now_add=True)

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD, default="card")
    payment_status = models.CharField(
        max_length=50, choices=[("paid", "Paid"), ("unpaid", "Unpaid")], default="unpaid"
    )
    
    order_status = models.CharField(max_length=20, choices=ORDER_STATUS, default="pending")

    razorpay_order_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
 

    class Meta:
        db_table = "invoice"
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        ordering = ["-invoice_date"]
        indexes = [
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["invoice_date"]),
            models.Index(fields=["order_status"]),
        ]

    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.invoice_date}"

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            for item in self.items.all():
                item.delete()
            super().delete(*args, **kwargs)
    
    def recalc_total(self):
        subtotal = sum((item.subtotal for item in self.items.all()), Decimal("0.00"))
        discount = self.discount if isinstance(self.discount, Decimal) else Decimal(str(self.discount))
        tax = self.tax if isinstance(self.tax, Decimal) else Decimal(str(self.tax))
        self.total_amount = subtotal - discount + tax
        self.save(update_fields=["total_amount"])

class InvoiceItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    invoice = models.ForeignKey(
        "product_sales.Invoice",
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        "product_sales.Product",
        on_delete=models.CASCADE,
        related_name="invoice_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        db_table = "invoice_item"
        verbose_name = "Invoice Item"
        verbose_name_plural = "Invoice Items"
        ordering = ["invoice"]
        indexes = [
            models.Index(fields=["invoice"]),
            models.Index(fields=["product"]),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.quantity}"
    
    @property
    def subtotal(self):
        return self.price * self.quantity
    
    def clean(self):
        if self._state.adding and self.quantity > self.product.current_stock:
            raise ValidationError(
                f"Not enough stock for {self.product.name}. "
                f"Available: {self.product.current_stock}, requested: {self.quantity}"
            )

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        old_quantity = None if is_new else InvoiceItem.objects.get(pk=self.pk).quantity

        with transaction.atomic():
            # Lock the product row first so concurrent sales serialise on it
            # rather than both reading the same pre-sale stock level.
            product = (
                Product.objects.select_for_update().get(pk=self.product_id)
            )

            delta = self.quantity if is_new else self.quantity - old_quantity

            if delta > product.current_stock:
                # current_stock is a PositiveIntegerField: letting this through
                # produced a raw database constraint error instead of a message
                # the caller can act on.
                raise ValidationError(
                    f"Not enough stock for {product.name}. "
                    f"Available: {product.current_stock}, requested: {delta}"
                )

            super().save(*args, **kwargs)

            product.current_stock = models.F("current_stock") - delta
            product.save(update_fields=["current_stock"])
            product.refresh_from_db(fields=["current_stock"])
            self.product = product

        self.invoice.recalc_total()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            product = (
                Product.objects.select_for_update().get(pk=self.product_id)
            )
            product.current_stock = models.F("current_stock") + self.quantity  # restore stock
            product.save(update_fields=["current_stock"])
            super().delete(*args, **kwargs)
        self.invoice.recalc_total()