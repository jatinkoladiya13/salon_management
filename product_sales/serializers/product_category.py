from rest_framework import serializers
from product_sales.models import ProductCategory

class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = '__all__'
        read_only_fields = ('id',)

    def create(self, validated_data):
        validated_data["is_active"] = True
        return super().create(validated_data) 