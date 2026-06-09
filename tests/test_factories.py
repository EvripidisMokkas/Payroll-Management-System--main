from django.test import TestCase

from tests import factories


class CrossDomainFactoryTests(TestCase):
    def test_factories_cover_every_domain_boundary(self):
        tenant = factories.organization()
        actor = factories.user()
        factories.membership(member=actor, tenant=tenant)

        worker = factories.employee(tenant=tenant)
        period = factories.payroll_period(tenant=tenant)
        created = [
            actor,
            tenant,
            worker,
            factories.client(tenant=tenant),
            factories.payroll_input(period=period, worker=worker),
            factories.jurisdiction(),
            factories.ledger_entry(tenant=tenant),
            factories.document(tenant=tenant, owner=actor),
            factories.audit_event(tenant=tenant, actor=actor),
            factories.risk_entry(tenant=tenant, owner=actor),
        ]
        analytics_tenant, analytics_actor, analytics_entry = factories.analytics_context()

        self.assertTrue(all(instance.pk for instance in created))
        self.assertEqual(analytics_entry.organization, analytics_tenant)
        self.assertTrue(analytics_actor.organization_memberships.filter(organization=analytics_tenant).exists())
