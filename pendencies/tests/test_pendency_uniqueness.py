"""
Tests for AllocationPendency partial unique constraint and deduplication.

Contract: at most one AllocationPendency per employee where allocation IS NULL.
Allocation-level uniqueness (OneToOneField) remains untouched.
"""

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from employees.models import Employee
from pendencies.models import AllocationPendency
from users.models import SystemUser


def _make_employee(eid="E01", email="emp1@corp.com", full_name=None):
    return Employee.objects.create(
        full_name=full_name or f"Test Employee {eid}",
        corporate_email=email,
        employee_id=eid,
    )


def _make_user(email="tech@corp.com"):
    return SystemUser.objects.create_user(email=email, password="pass", role="admin")


class AllocationPendencyNullConstraintTest(TestCase):
    """DB-level partial unique constraint tests."""

    def setUp(self):
        self.emp = _make_employee()

    def test_first_employee_level_pendency_succeeds(self):
        p = AllocationPendency.objects.create(employee=self.emp, allocation=None)
        self.assertIsNotNone(p.pk)

    def test_second_employee_level_pendency_raises_integrity_error(self):
        AllocationPendency.objects.create(employee=self.emp, allocation=None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AllocationPendency.objects.create(employee=self.emp, allocation=None)

    def test_different_employees_can_each_have_null_allocation_pendency(self):
        emp2 = _make_employee(eid="E02", email="emp2@corp.com")
        AllocationPendency.objects.create(employee=self.emp, allocation=None)
        p2 = AllocationPendency.objects.create(employee=emp2, allocation=None)
        self.assertIsNotNone(p2.pk)

    def test_get_or_create_returns_existing_row(self):
        created_obj, created = AllocationPendency.objects.get_or_create(
            employee=self.emp, allocation=None
        )
        fetched_obj, fetched = AllocationPendency.objects.get_or_create(
            employee=self.emp, allocation=None
        )
        self.assertFalse(fetched)
        self.assertEqual(created_obj.pk, fetched_obj.pk)


class DeduplicationDataMigrationTest(TestCase):
    """
    Tests that simulate the deduplication logic from the data migration.

    We call the migration function directly via apps/schema_editor to verify
    it selects the canonical row correctly and merges fields.
    """

    def _run_dedup(self):
        from django.db.migrations.state import ProjectState
        from pendencies.migrations import (
            _0005_deduplicate_employee_null_allocation as migration_module,
        )

        migration_module.deduplicate_employee_null_pendencies(
            __import__("django.apps", fromlist=["apps"]).apps,
            connection.schema_editor(),
        )

    def setUp(self):
        self.emp = _make_employee()
        self.tech = _make_user()

    def _create_raw(self, **kwargs):
        """Insert AllocationPendency bypassing the partial unique constraint.

        Drops the partial index first (SQLite DDL is transactional, so TestCase
        rollback recreates it automatically after the test).
        """
        defaults = dict(
            employee_id=self.emp.pk,
            allocation_id=None,
            action="no_action",
            observation="",
            technical_responsible_id=None,
            last_submitted_action=None,
            last_action_changed_at=None,
            pendency_submitted_at=None,
            resolved_at=None,
            updated_by_id=None,
        )
        defaults.update(kwargs)
        with connection.cursor() as cur:
            cur.execute(
                "DROP INDEX IF EXISTS uq_pendency_employee_without_allocation"
            )
            cur.execute(
                """
                INSERT INTO pendencies_allocationpendency
                    (employee_id, allocation_id, action, observation,
                     technical_responsible_id, last_submitted_action,
                     last_action_changed_at, pendency_submitted_at,
                     resolved_at, updated_by_id, created_at, updated_at)
                VALUES
                    (?, ?, ?, ?,
                     ?, ?,
                     ?, ?,
                     ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                [
                    defaults["employee_id"],
                    defaults["allocation_id"],
                    defaults["action"],
                    defaults["observation"],
                    defaults["technical_responsible_id"],
                    defaults["last_submitted_action"],
                    defaults["last_action_changed_at"],
                    defaults["pendency_submitted_at"],
                    defaults["resolved_at"],
                    defaults["updated_by_id"],
                ],
            )
            return cur.lastrowid

    def test_dedup_keeps_open_over_no_action(self):
        """open row (action != no_action) wins over no_action."""
        from pendencies.migrations._0005_deduplicate_employee_null_allocation import (
            deduplicate_employee_null_pendencies,
        )
        import django.apps

        id_closed = self._create_raw(action="no_action")
        id_open = self._create_raw(action="pending")

        deduplicate_employee_null_pendencies(django.apps.apps, connection.schema_editor())

        remaining = list(
            AllocationPendency.objects.filter(
                employee=self.emp, allocation__isnull=True
            ).values_list("id", "action")
        )
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0][0], id_open)
        self.assertEqual(remaining[0][1], "pending")

    def test_dedup_keeps_row_with_responsible(self):
        """When both no_action, row with technical_responsible wins."""
        from pendencies.migrations._0005_deduplicate_employee_null_allocation import (
            deduplicate_employee_null_pendencies,
        )
        import django.apps

        id_no_resp = self._create_raw(action="no_action", technical_responsible_id=None)
        id_with_resp = self._create_raw(
            action="no_action", technical_responsible_id=self.tech.pk
        )

        deduplicate_employee_null_pendencies(django.apps.apps, connection.schema_editor())

        remaining = list(
            AllocationPendency.objects.filter(
                employee=self.emp, allocation__isnull=True
            ).values_list("id", flat=True)
        )
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0], id_with_resp)

    def test_dedup_merges_observation_into_canonical(self):
        """Canonical keeps its own observation; if empty, takes duplicate's."""
        from pendencies.migrations._0005_deduplicate_employee_null_allocation import (
            deduplicate_employee_null_pendencies,
        )
        import django.apps

        # canonical has empty obs; duplicate has useful obs
        id_canonical = self._create_raw(action="pending", observation="")
        self._create_raw(action="no_action", observation="useful note")

        deduplicate_employee_null_pendencies(django.apps.apps, connection.schema_editor())

        p = AllocationPendency.objects.get(employee=self.emp, allocation__isnull=True)
        self.assertEqual(p.id, id_canonical)
        self.assertEqual(p.observation, "useful note")

    def test_dedup_does_not_touch_non_null_allocation_rows(self):
        """Rows with allocation_id IS NOT NULL are never touched."""
        from pendencies.migrations._0005_deduplicate_employee_null_allocation import (
            deduplicate_employee_null_pendencies,
        )
        import django.apps
        from allocations.models import LineAllocation
        from telecom.models import PhoneLine, SIMcard

        sim = SIMcard.objects.create(iccid="123456789012345678")
        line = PhoneLine.objects.create(phone_number="11900000001", sim_card=sim)
        alloc = LineAllocation.objects.create(employee=self.emp, phone_line=line)

        p_with_alloc = AllocationPendency.objects.create(
            employee=self.emp, allocation=alloc
        )
        id_null = self._create_raw(action="no_action")

        deduplicate_employee_null_pendencies(django.apps.apps, connection.schema_editor())

        # allocation-level row must still exist
        self.assertTrue(
            AllocationPendency.objects.filter(pk=p_with_alloc.pk).exists()
        )
        # null-allocation row still exists (only one, so no dedup needed)
        self.assertEqual(
            AllocationPendency.objects.filter(
                employee=self.emp, allocation__isnull=True
            ).count(),
            1,
        )
