from django.db import models
from datetime import timezone
from django.utils import timezone as dj_timezone

# Create your models here.


class CallCredit(models.Model):
    CREDIT_TYPE_CHOICE = (
        ('subscription', 'subscription'),
        ('credits', 'credits'),
    )

    credits_sec = models.IntegerField(default=0)
    credit_type = models.CharField(max_length=20, choices=CREDIT_TYPE_CHOICE)
    expiry_date = models.DateField()

    created_on = models.DateTimeField(auto_now_add=True)
    expired = models.BooleanField(default=False)

    def is_expired(self):
        return self.expiry_date < timezone.now().astimezone(timezone.utc).date()
    
    @classmethod
    def add_call_credits(cls, credit_sec, credit_type, expiry_date):
        return cls.objects.create(credits_sec=credit_sec, credit_type=credit_type, expiry_date=expiry_date)

    @classmethod
    def deduct_credits(cls, seconds):
        now = timezone.now().astimezone(timezone.utc)
        soon_expiring_credits = cls.objects.filter(expiry_date__gte=now.date()).order_by('expiry_date')
        deducted_credits = 0
        for credit in soon_expiring_credits:
            if credit.credits_sec > 0:
                if credit.is_expired():
                    credit.expired = True
                    credit.save()
                    continue
                if credit.credits_sec <= seconds - deducted_credits:
                    deducted_credits += credit.credits_sec
                    credit.credits_sec = 0
                    credit.save()
                else:
                    credit.credits_sec -= seconds - deducted_credits
                    credit.save()
                    deducted_credits = seconds
                    break
        if deducted_credits < seconds:
            return seconds - deducted_credits
        return 0
    
    @classmethod
    def all_call_credits(cls):
        """
        return expiry wise credit
        :return:
        """
        now = dj_timezone.now()
        return cls.objects.filter(
            expired=False,
            expiry_date__gte=now.date()
        ).order_by('expiry_date')

    @classmethod
    def is_balance_exhausted(cls):
        return cls.objects.filter(credits_sec__gt=0).count() == 0

    @classmethod
    def available_credits(cls):
        """
        return sum of all credit available
        :return:
        """
        now = dj_timezone.now()
        return cls.objects.filter(expiry_date__gte=now.date(),
                                  expired=False).aggregate(
            total_credits=models.Sum('credits_sec'))['total_credits'] or 0

    @classmethod
    def current_subscription_available_min(cls):
        """
        return last active subscription available min
        :return:
        """
        now = dj_timezone.now()
        filtered_obj = cls.objects.filter(
            expiry_date__gte=now.date(),
            expired=False,
            credit_type='subscription'
        ).order_by('-id').first()

        return filtered_obj.credits_sec if filtered_obj else 0

    class Meta:
        db_table = 'call_credit'
        verbose_name = 'Call Credit'
        verbose_name_plural = 'Call Credits'

    