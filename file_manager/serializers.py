from rest_framework import serializers
from .models import UploadedFile, SiteConfiguration

class UploadedFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = UploadedFile
        fields = ['id', 'file', 'file_url', 'uploaded_at', 'file_size']
        read_only_fields = ['id', 'uploaded_at', 'file_size', 'file_url']

    def get_file_url(self, obj):
        return obj.file.url

    def validate_file(self, value):
        max_size_mb = SiteConfiguration.get().max_file_size_mb
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"File size must not exceed {max_size_mb} MB."
            )
        return value