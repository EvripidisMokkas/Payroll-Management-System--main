import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("organizations", "0002_organization_legal_billing_lifecycle"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="RiskRegisterEntry", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("title", models.CharField(max_length=200)), ("description", models.TextField()), ("likelihood", models.PositiveSmallIntegerField(choices=[(1, "Rare"), (2, "Unlikely"), (3, "Possible"), (4, "Likely"), (5, "Almost certain")])), ("impact", models.PositiveSmallIntegerField(choices=[(1, "Insignificant"), (2, "Minor"), (3, "Moderate"), (4, "Major"), (5, "Severe")])), ("mitigation", models.TextField()), ("review_date", models.DateField(db_index=True)), ("status", models.CharField(choices=[("open", "Open"), ("mitigating", "Mitigating"), ("accepted", "Accepted"), ("closed", "Closed")], db_index=True, default="open", max_length=20)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization")), ("owner", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_risks", to=settings.AUTH_USER_MODEL))], options={"indexes": [models.Index(fields=["organization", "status", "review_date"], name="risk_org_status_review_idx")]})]
