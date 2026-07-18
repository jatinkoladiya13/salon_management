from django.db import models, transaction
import uuid

# Create your models here.

class StockPurchase(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier_details = models.JSONField(blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    purchase_date = models.DateField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    payment_status = models.CharField(max_length=50, choices=[('paid', 'Paid'), ('unpaid', 'Unpaid')], default='unpaid')

    class Meta:
        db_table = "stock_purchase"
        verbose_name = "Stock Purchase"
        verbose_name_plural = "Stock Purchases"
        ordering = ["-purchase_date"]
        indexes = [
            models.Index(fields=["purchase_date"]),
            models.Index(fields=["payment_status"]),
        ]

    def __str__(self):
        return f"Purchase {self.invoice_number} - {self.purchase_date}"

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            for item in self.items.all():
                item.delete()  # This will trigger each item's delete method
            super().delete(*args, **kwargs)

    def recalc_total(self):
        total = sum(item.subtotal for item in self.items.all())
        self.total_amount = total
        self.save(update_fields=["total_amount"])     
