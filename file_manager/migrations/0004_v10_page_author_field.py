from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('file_manager', '0003_v9_deleted_state_and_base_fields')]

    operations = [
        migrations.AddField(
            model_name='page',
            name='author',
            field=models.CharField(blank=True, max_length=255, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='pagepublication',
            name='author',
            field=models.CharField(blank=True, max_length=255, default=''),
            preserve_default=False,
        ),
    ]
