from django.db import models
from salon_management.behaviours import DateMixin
from autoslug import AutoSlugField
# Create your models here.

class SalonDetails(DateMixin, models.Model):
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

class SalonOpeningHour(models.Model):
    WEEK_DAYS = (
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
    )

    salon = models.ForeignKey(SalonDetails, on_delete=models.CASCADE, related_name="opening_hours")

    day  = models.CharField(max_length=10, choices=WEEK_DAYS)
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        unique_together = ("salon", "day")

    def __str__(self):
        return f"{self.salon.name} - {self.day}"