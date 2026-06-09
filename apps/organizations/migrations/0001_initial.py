from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="Organization", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=200)), ("slug", models.SlugField(unique=True)), ("is_active", models.BooleanField(default=True))]),
        migrations.CreateModel(name="OrganizationMembership", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("role", models.CharField(choices=[("administrator", "Administrator"), ("payroll_operator", "Payroll operator"), ("employee", "Employee"), ("auditor", "Auditor"), ("client", "Client")], max_length=32)), ("is_active", models.BooleanField(default=True)), ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="organizations.organization")), ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="organization_memberships", to=settings.AUTH_USER_MODEL))]),
        migrations.AddConstraint(model_name="organizationmembership", constraint=models.UniqueConstraint(fields=("user", "organization"), name="unique_user_organization")),
    ]
