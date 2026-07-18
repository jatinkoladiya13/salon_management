from django.apps import AppConfig


class ProductSalesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'product_sales'

    def ready(self):
        import product_sales.signals  # noqa
