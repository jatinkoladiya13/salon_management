from django.core.exceptions import ValidationError
from django.db import models, transaction

import uuid

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

    invoice_date = models.DateField(auto_now_add=True)

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD, default="card")
    payment_status = models.CharField(
        max_length=50, choices=[("paid", "Paid"), ("unpaid", "Unpaid")], default="unpaid"
    )

    
    order_status = models.CharField(max_length=20, choices=ORDER_STATUS, default="pending")
    
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
        subtotal = sum(item.subtotal for item in self.items.all())
        self.total_amount = subtotal - self.discount + self.tax
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
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

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
            super().save(*args, **kwargs)
 
            product = self.product
            if is_new:
                product.current_stock = models.F("current_stock") - self.quantity
            else:
                diff = self.quantity - old_quantity
                product.current_stock = models.F("current_stock") - diff
            product.save(update_fields=["current_stock"])
 
        self.invoice.recalc_total()
 
    def delete(self, *args, **kwargs):
        with transaction.atomic():
            product = self.product
            product.current_stock = models.F("current_stock") + self.quantity  # restore stock
            product.save(update_fields=["current_stock"])
            super().delete(*args, **kwargs)
        self.invoice.recalc_total()