from decimal import Decimal

from django.test import TestCase

from apps.auditing.models import AuditAction, AuditEvent
from apps.auditing.services import export_audit_events, record_event
from apps.organizations.models import OrganizationRole
from apps.payroll.models import InputType, PayrollLifecycle
from apps.payroll.services import create_adjustment_run, process_payroll, transition_period
from apps.taxation.services.engine import TaxEngineRegistry, UnsupportedJurisdictionError
from tests import factories


class CompletePayrollLifecycleTests(TestCase):
    def test_process_approve_pay_correct_and_export_evidence(self):
        tenant = factories.organization()
        operator = factories.user()
        admin = factories.user()
        factories.membership(member=operator, tenant=tenant, role=OrganizationRole.PAYROLL_OPERATOR)
        factories.membership(member=admin, tenant=tenant, role=OrganizationRole.ADMINISTRATOR)
        period = factories.payroll_period(tenant=tenant)
        worker = factories.employee(tenant=tenant)
        factories.payroll_input(period=period, worker=worker, amount=Decimal("1000.005"))

        original = process_payroll(period=period, idempotency_key="regular-run", actor=operator)
        for status, actor in (
            (PayrollLifecycle.VALIDATION, operator),
            (PayrollLifecycle.APPROVAL, admin),
            (PayrollLifecycle.LOCKED, admin),
            (PayrollLifecycle.PAID, operator),
        ):
            period = transition_period(period=period, to_status=status, actor=actor, explanation=f"Move to {status}")

        correction = create_adjustment_run(
            original_period=period,
            inputs=[{"employee_id": worker.pk, "input_type": InputType.BONUS, "amount": "-10.005"}],
            reason="Correction after payment",
            idempotency_key="correction-run",
            actor=admin,
        )
        period = transition_period(period=period, to_status=PayrollLifecycle.CORRECTED, actor=admin)
        record_event(
            organization=tenant,
            actor=admin,
            action=AuditAction.EXPORT,
            object_type="payroll.PayrollPeriod",
            object_id=period.pk,
            after={"original_run": original.pk, "correction_run": correction.pk},
        )
        content, content_type, metadata = export_audit_events(AuditEvent.objects.for_organization(tenant), "json")

        self.assertEqual(original.net_pay, Decimal("1000.01"))
        self.assertEqual(correction.net_pay, Decimal("-10.01"))
        self.assertEqual(period.status, PayrollLifecycle.CORRECTED)
        self.assertEqual(period.approvals.count(), 5)
        self.assertEqual(content_type, "application/json")
        self.assertEqual(metadata["record_count"], 1)
        self.assertIn(b"correction_run", content)


class TaxAdapterContractTests(TestCase):
    def test_unregistered_taxation_adapter_fails_closed(self):
        registry = TaxEngineRegistry()
        jurisdiction = factories.jurisdiction(calculator_key="missing-adapter")
        with self.assertRaises(UnsupportedJurisdictionError):
            registry.resolve(jurisdiction)
