from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("organizations", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="PayrollRecord", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("employee_name", models.CharField(max_length=200)), ("gross_amount", models.DecimalField(decimal_places=2, max_digits=12)), ("status", models.CharField(default="draft", max_length=20)), ("employee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="payroll_records", to=settings.AUTH_USER_MODEL)), ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"))], options={"permissions": [("operate_payroll", "Can create and update payroll operations")]})]
