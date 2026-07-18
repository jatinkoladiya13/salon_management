from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import *

router = DefaultRouter()

router.register(r'product-categories', ProductCategoryViewSet, basename='product-category')
router.register(r'products', ProductViewSet, basename='product')

router.register(r'cart-items', CartItemViewSet, basename='cart-item')
router.register(r'invoices', InvoiceViewSet, basename='invoice')


urlpatterns = [
    path('', include(router.urls)),
]
