from django.db import migrations

import apps.security.fields


def encrypt_existing_mfa_secrets(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.exclude(mfa_secret="").iterator(chunk_size=500):
        user.save(update_fields=("mfa_secret",))


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [
        migrations.AlterField(
            model_name="user",
            name="mfa_secret",
            field=apps.security.fields.EncryptedTextField(blank=True),
        ),
        migrations.RunPython(encrypt_existing_mfa_secrets, migrations.RunPython.noop),
    ]
