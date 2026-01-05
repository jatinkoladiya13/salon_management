import os
from celery import Celery
from tenant_schemas_celery.task import TenantTask
from django.conf import settings
from django.core.mail import EmailMessage
from tenant_schemas_celery.app import CeleryApp as TenantAwareCeleryApp


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "salon_management.settings")

app  = TenantAwareCeleryApp()

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(base=TenantTask, bind=True)
def send_mail(self, subject, body, recipient, content_subtype="plain"):
    print("send_email")
    mail = EmailMessage(subject, body, "khodalenterprise557@gmail.com", to=[recipient])
    mail.content_subtype = content_subtype 
    mail.send()
    print("after send_mail")

