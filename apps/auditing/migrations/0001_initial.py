from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("organizations", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name="AuditAnnotation", fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("note", models.TextField()), ("created_at", models.DateTimeField(auto_now_add=True)), ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)), ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="organizations.organization"))], options={"permissions": [("annotate_audit", "Can add authorized audit annotations")]})]
