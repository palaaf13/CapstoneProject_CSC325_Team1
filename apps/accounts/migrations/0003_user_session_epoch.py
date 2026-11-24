from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_copy_legacy_auth_users"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="session_epoch",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
