from django.db import migrations, models


def strip_sha256_prefix(apps, schema_editor):
    PackageVersion = apps.get_model('file_manager', 'PackageVersion')
    rows = PackageVersion.objects.filter(content_hash__startswith='sha256:')
    for pv in rows:
        pv.content_hash = pv.content_hash[len('sha256:'):]
        pv.save(update_fields=['content_hash'])


class Migration(migrations.Migration):

    dependencies = [
        ('file_manager', '0002_remove_pagepublication_package_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='packageversion',
            old_name='tombstoned_at',
            new_name='deleted_at',
        ),
        migrations.RenameField(
            model_name='packageversion',
            old_name='tombstone_reason',
            new_name='delete_reason',
        ),
        migrations.AddField(
            model_name='packageversion',
            name='base_name',
            field=models.CharField(blank=True, max_length=255, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='packageversion',
            name='base_version',
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.RunPython(strip_sha256_prefix, migrations.RunPython.noop),
    ]
