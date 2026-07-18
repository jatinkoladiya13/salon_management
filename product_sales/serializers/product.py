from rest_framework import serializers
from product_sales.models import Product
from product_sales.models.product_image import ProductImage


import os

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "is_active")
        read_only_fields = ("id", "is_active")

class ProductSerializer(serializers.ModelSerializer):

    # Display existing images
    product_images = ProductImageSerializer(
        source="images",
        many=True,
        read_only=True
    )

    # Upload multiple images
    images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )
    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "product_category",
            "unit",
            "current_stock",
            "minimum_stock",
            "purchase_price",
            "selling_price",
            "is_active",
            "images",
            "product_images",
        ) 
        read_only_fields = ('id',)
        extra_kwargs = {
            "product_category": {"required": True},
            "name": {"required": True},
            "selling_price": {"required": True},
        }

    def validate(self, attrs):
        """
        Require at least one image when creating a product.
        """
        if self.instance is None:  # Create
            images = attrs.get("images")

            if not images:
                raise serializers.ValidationError("At least one product image is required.")

        return attrs
    

    def validate_images(self, images):
        allowed_extensions = {".jpg", ".jpeg", ".png", ".webp"}

        for image in images:
            ext = os.path.splitext(image.name)[1].lower()

            if ext not in allowed_extensions:
                raise serializers.ValidationError(
                    f"{image.name}: Only JPG, JPEG, PNG and WEBP images are allowed."
                )

            if image.size > 10 * 1024 * 1024:
                raise serializers.ValidationError(
                    f"{image.name}: Image size cannot exceed 10 MB."
                )

        return images
    

    def create(self, validated_data):
        images = validated_data.pop("images", [])

        product = Product.objects.create(**validated_data)

        ProductImage.objects.bulk_create(
            [
                ProductImage(product=product, image=image)
                for image in images
            ]
        )

        return product
    
    def update(self, instance, validated_data):
        images = validated_data.pop("images", None)

        # Update Product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # Replace old images with new ones (optional behavior)
        if images is not None:
            instance.images.all().delete()

            ProductImage.objects.bulk_create(
                [
                    ProductImage(product=instance, image=image)
                    for image in images
                ]
            )

        return instance
        