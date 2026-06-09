"""Jurisdiction-aware filing export generation."""

import csv
import hashlib
import io
import json

from django.core.exceptions import ValidationError

from apps.taxation.models import FilingExport


def create_filing_export(filing_period, export_format, *, amendment=None):
    if export_format not in filing_period.jurisdiction.filing_export_formats:
        raise ValidationError(f"Unsupported export format '{export_format}' for {filing_period.jurisdiction.code}.")
    rows = list(filing_period.liabilities.values("liability_type", "amount", "payment_reference"))
    if export_format == "json":
        payload = json.dumps(rows, default=str, sort_keys=True)
    elif export_format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=("liability_type", "amount", "payment_reference"))
        writer.writeheader()
        writer.writerows(rows)
        payload = output.getvalue()
    else:
        raise ValidationError(f"No exporter is implemented for '{export_format}'.")
    return FilingExport.objects.create(
        organization=filing_period.organization,
        filing_period=filing_period,
        amendment=amendment,
        format=export_format,
        payload=payload,
        checksum=hashlib.sha256(payload.encode()).hexdigest(),
    )
