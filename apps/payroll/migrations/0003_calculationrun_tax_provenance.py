from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payroll", "0002_payroll_domain"), ("taxation", "0001_initial")]
    operations = [
        migrations.AddField(model_name="calculationrun", name="tax_jurisdiction_code", field=models.CharField(default="not_applicable", max_length=32)),
        migrations.AddField(model_name="calculationrun", name="tax_rule_version", field=models.CharField(default="not_applicable", max_length=80)),
    ]
