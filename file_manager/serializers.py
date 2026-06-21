from rest_framework import serializers

from .models import Package, PackageAlias, PackageVersion, Page
from .pages import page_url


class PackageVersionSerializer(serializers.ModelSerializer):
    package = serializers.CharField(source='package.name', read_only=True)
    author = serializers.CharField(source='author.name', read_only=True)
    date = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    deleted = serializers.SerializerMethodField()
    base = serializers.SerializerMethodField()

    class Meta:
        model = PackageVersion
        fields = [
            'package',
            'version',
            'author',
            'date',
            'summary',
            'description',
            'content_hash',
            'download_url',
            'deleted',
            'delete_reason',
            'base',
        ]

    def get_date(self, obj):
        return obj.render_uploaded_at()

    def get_download_url(self, obj):
        if obj.is_deleted:
            return None
        return f'/api/packages/{obj.package.name}/versions/{obj.version}/download'

    def get_deleted(self, obj):
        return obj.is_deleted

    def get_base(self, obj):
        if obj.base_name:
            return {'name': obj.base_name, 'version': obj.base_version}
        return None


class PackageAliasSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(source='version.version', read_only=True)

    class Meta:
        model = PackageAlias
        fields = ['name', 'version', 'updated_at']


class PackageListItemSerializer(serializers.ModelSerializer):
    latest_version = serializers.SerializerMethodField()
    versions_count = serializers.SerializerMethodField()

    class Meta:
        model = Package
        fields = ['name', 'latest_version', 'versions_count', 'created_at']

    def get_latest_version(self, obj):
        latest = obj.versions.filter(deleted_at__isnull=True).order_by('-version').first()
        if latest is None:
            return None
        return PackageVersionSerializer(latest).data

    def get_versions_count(self, obj):
        return obj.versions.count()


class PackageDetailSerializer(serializers.ModelSerializer):
    versions = serializers.SerializerMethodField()
    aliases = serializers.SerializerMethodField()

    class Meta:
        model = Package
        fields = ['name', 'created_at', 'versions', 'aliases']

    def get_versions(self, obj):
        qs = obj.versions.order_by('-version').select_related('author')
        return PackageVersionSerializer(qs, many=True).data

    def get_aliases(self, obj):
        qs = obj.aliases.select_related('version').order_by('name')
        return PackageAliasSerializer(qs, many=True).data


class PageSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    published_at = serializers.SerializerMethodField()
    published_by = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = ['path', 'url', 'published_at', 'published_by', 'content_hash']

    def get_url(self, obj):
        return page_url(obj.organisation, obj.path)

    def get_published_at(self, obj):
        return obj.published_at.strftime('%Y-%m-%dT%H:%M:%SZ')

    def get_published_by(self, obj):
        return (
            obj.author
            or (obj.published_by.get_username() if obj.published_by else 'service')
        )
