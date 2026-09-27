from django.db import models

import uuid

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)

    product_category = models.ForeignKey(
        "product_sales.ProductCategory",
        on_delete=models.CASCADE,
        related_name="products",
    )


    unit = models.CharField(max_length=50, blank=True, null=True)
    current_stock = models.PositiveIntegerField(default=0)
    minimum_stock = models.PositiveIntegerField(default=0)
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "product"
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["product_category"]),
        ]

    def __str__(self):
        return self.name
    
    @property
    def is_low_stock(self):
        return self.current_stock <= self.minimum_stock
 
    @property
    def is_in_stock(self):
        return self.current_stock > 0
 
    def primary_image(self):
        return self.images.filter(is_active=True).first()
     



