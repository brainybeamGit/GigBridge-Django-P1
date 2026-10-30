from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('client', '0015_bookmark'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='image',
            field=models.ImageField(blank=True, help_text='Project featured/cover image', null=True, upload_to='project_images/'),
        ),
    ]

