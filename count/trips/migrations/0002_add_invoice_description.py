from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trips", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="description",
            field=models.TextField(blank=True, verbose_name="Descripción"),
        ),
    ]
