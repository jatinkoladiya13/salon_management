from django.db import models
from salon_management.behaviours import DateMixin
from autoslug import AutoSlugField
# Create your models here.

import uuid

class SalonDetails(DateMixin, models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=255, blank=True, null=True)
    slug = AutoSlugField(populate_from="name", unique=True)
    
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    organization_email = models.EmailField(blank=True, null=True)

    company_logo = models.ImageField(
        verbose_name="company_logo",
        upload_to="company_logo/",
        null=True,
        blank=True,
    )
    
    description = models.CharField(max_length=255, blank=True, null=True)

    status_choices = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )
    status = models.CharField(max_length=10, choices=status_choices)

    location_url = models.URLField(null=True, blank=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    postal_code = models.CharField(max_length=20, blank=True, null=True)
    
    class Meta:
        db_table = "salon_details"
        verbose_name = "Salon Detail"
        verbose_name_plural = "Salon Details"
        ordering = ("id",)
        indexes = [models.Index(fields=["name"])]

    def __str__(self) -> str:
        return self.name if self.name else str(self.id)    

