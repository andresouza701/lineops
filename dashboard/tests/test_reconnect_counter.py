"""
Tests for the reconectados counter fix.

Root cause: build_admin_resolved_reconnect_numbers_for_day reads
DailyUserAction which is no longer written by the new AllocationPendency
UI. The fix adds build_pendency_resolved_reconnect_numbers_for_day which
reads AllocationPendency where last_submitted_action=RECONNECT_WHATSAPP
and resolved_at.date==today.
"""
from datetime import datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from allocations.models import LineAllocation
from dashboard.views import (
    build_pendency_resolved_reconnect_numbers_for_day,
    build_reconnected_numbers_for_day,
)
from employees.models import Employee
from pendencies.models import AllocationPendency
from telecom.models import PhoneLine, SIMcard


def _make_sim(iccid="89000000000000000001", carrier="Vivo"):
    return SIMcard.objects.create(iccid=iccid, carrier=carrier)


def _make_line(number="+5511999990001", sim=None):
    if sim is None:
        sim = _make_sim(iccid=number[-10:].replace("+", "0"))
    return PhoneLine.objects.create(phone_number=number, sim_card=sim)


def _make_employee(email="super@corp.com", eid="E01", full_name=None):
    return Employee.objects.create(
        full_name=full_name or f"Test Employee {eid}",
        corporate_email=email,
        employee_id=eid,
    )


def _make_allocation(employee, phone_line, allocated_at=None, released_at=None):
    # allocated_at is auto_now_add — create active first, then back-date both
    # timestamps via queryset update (bypasses auto_now_add, satisfies constraints).
    alloc = LineAllocation.objects.create(
        employee=employee,
        phone_line=phone_line,
        is_active=True,
    )
    update_kwargs = {}
    if allocated_at is not None:
        update_kwargs["allocated_at"] = allocated_at
    if released_at is not None:
        update_kwargs["released_at"] = released_at
        update_kwargs["is_active"] = False
    if update_kwargs:
        LineAllocation.objects.filter(pk=alloc.pk).update(**update_kwargs)
        for k, v in update_kwargs.items():
            setattr(alloc, k, v)
    return alloc


class LastSubmittedActionModelTest(TestCase):
    """Unit tests for AllocationPendency.record_action_change setting
    last_submitted_action."""

    def setUp(self):
        self.employee = _make_employee()
        self.pendency = AllocationPendency.objects.create(
            employee=self.employee,
            allocation=None,
        )

    def test_last_submitted_action_set_on_first_submit(self):
        self.pendency.record_action_change(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            actor_role="super",
        )
        self.assertEqual(
            self.pendency.last_submitted_action,
            AllocationPendency.ActionType.RECONNECT_WHATSAPP,
        )

    def test_last_submitted_action_set_to_new_number(self):
        self.pendency.record_action_change(
            AllocationPendency.ActionType.NEW_NUMBER,
            actor_role="super",
        )
        self.assertEqual(
            self.pendency.last_submitted_action,
            AllocationPendency.ActionType.NEW_NUMBER,
        )

    def test_last_submitted_action_not_cleared_on_resolution(self):
        """After resolution (NO_ACTION), last_submitted_action must stay."""
        self.pendency.record_action_change(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            actor_role="super",
        )
        # Admin resolves
        self.pendency.record_action_change(
            AllocationPendency.ActionType.NO_ACTION,
            actor_role="admin",
        )
        # last_submitted_action must still reflect what was resolved
        self.assertEqual(
            self.pendency.last_submitted_action,
            AllocationPendency.ActionType.RECONNECT_WHATSAPP,
        )

    def test_last_submitted_action_updated_on_reopen_with_different_action(self):
        self.pendency.record_action_change(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            actor_role="super",
        )
        # Admin resolves
        self.pendency.record_action_change(
            AllocationPendency.ActionType.NO_ACTION, actor_role="admin"
        )
        # Super reopens with a different action
        self.pendency.record_action_change(
            AllocationPendency.ActionType.NEW_NUMBER, actor_role="super"
        )
        self.assertEqual(
            self.pendency.last_submitted_action,
            AllocationPendency.ActionType.NEW_NUMBER,
        )

    def test_last_submitted_action_not_set_on_admin_direct_no_action(self):
        """Admin setting NO_ACTION on already-NO_ACTION pendency must not set
        field."""
        self.assertIsNone(self.pendency.last_submitted_action)
        self.pendency.record_action_change(
            AllocationPendency.ActionType.NO_ACTION, actor_role="admin"
        )
        # action was already NO_ACTION, so was_no_action=True and
        # is_now_no_action=True → the "if not is_now_no_action and was_no_action"
        # block does NOT run
        self.assertIsNone(self.pendency.last_submitted_action)


class BuildPendencyResolvedReconnectTest(TestCase):
    """
    Tests for build_pendency_resolved_reconnect_numbers_for_day.
    Validates that only RECONNECT_WHATSAPP resolved pendencies are counted.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.employee = _make_employee()
        self.line = _make_line()
        self.allocation = _make_allocation(self.employee, self.line)

    def _resolved_pendency(self, action_type, resolved_today=True):
        resolved_at = timezone.now() if resolved_today else (
            timezone.now() - timedelta(days=1)
        )
        return AllocationPendency.objects.create(
            employee=self.employee,
            allocation=self.allocation,
            action=AllocationPendency.ActionType.NO_ACTION,
            last_submitted_action=action_type,
            resolved_at=resolved_at,
            pendency_submitted_at=timezone.now() - timedelta(hours=2),
        )

    def test_counts_reconnect_whatsapp_resolved_today(self):
        self._resolved_pendency(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP
        )
        result = build_pendency_resolved_reconnect_numbers_for_day(self.today)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["numero"], self.line.phone_number)
        self.assertEqual(result[0]["usuario"], self.employee.full_name)

    def test_excludes_new_number_resolved_today(self):
        self._resolved_pendency(AllocationPendency.ActionType.NEW_NUMBER)
        result = build_pendency_resolved_reconnect_numbers_for_day(self.today)
        self.assertEqual(len(result), 0)

    def test_excludes_pending_resolved_today(self):
        self._resolved_pendency(AllocationPendency.ActionType.PENDING)
        result = build_pendency_resolved_reconnect_numbers_for_day(self.today)
        self.assertEqual(len(result), 0)

    def test_excludes_reconnect_resolved_yesterday(self):
        self._resolved_pendency(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            resolved_today=False,
        )
        result = build_pendency_resolved_reconnect_numbers_for_day(self.today)
        self.assertEqual(len(result), 0)

    def test_excludes_when_no_resolved_at(self):
        AllocationPendency.objects.create(
            employee=self.employee,
            allocation=self.allocation,
            action=AllocationPendency.ActionType.RECONNECT_WHATSAPP,
            last_submitted_action=(
                AllocationPendency.ActionType.RECONNECT_WHATSAPP
            ),
            resolved_at=None,
        )
        result = build_pendency_resolved_reconnect_numbers_for_day(self.today)
        self.assertEqual(len(result), 0)

    def test_filters_by_employee_ids(self):
        other_employee = _make_employee(email="other@corp.com", eid="E02")
        other_line = _make_line(number="+5511999990002")
        other_alloc = _make_allocation(other_employee, other_line)
        AllocationPendency.objects.create(
            employee=other_employee,
            allocation=other_alloc,
            action=AllocationPendency.ActionType.NO_ACTION,
            last_submitted_action=(
                AllocationPendency.ActionType.RECONNECT_WHATSAPP
            ),
            resolved_at=timezone.now(),
        )
        self._resolved_pendency(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP
        )

        # Scoped to self.employee only
        result = build_pendency_resolved_reconnect_numbers_for_day(
            self.today, employee_ids=[self.employee.id]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["numero"], self.line.phone_number)

    def test_multiple_reconnects_counted(self):
        second_employee = _make_employee(email="super2@corp.com", eid="E03")
        second_line = _make_line(number="+5511999990003")
        second_alloc = _make_allocation(second_employee, second_line)

        self._resolved_pendency(
            AllocationPendency.ActionType.RECONNECT_WHATSAPP
        )
        AllocationPendency.objects.create(
            employee=second_employee,
            allocation=second_alloc,
            action=AllocationPendency.ActionType.NO_ACTION,
            last_submitted_action=(
                AllocationPendency.ActionType.RECONNECT_WHATSAPP
            ),
            resolved_at=timezone.now(),
        )
        result = build_pendency_resolved_reconnect_numbers_for_day(self.today)
        self.assertEqual(len(result), 2)


class BuildReconnectedNumbersIntegrationTest(TestCase):
    """
    Integration test: build_reconnected_numbers_for_day aggregates both
    the ORM-based reconexoes and AllocationPendency-based reconexoes.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.employee = _make_employee()
        self.line = _make_line()

    def test_combines_orm_and_pendency_based_reconnects(self):
        # ORM-based: same employee, same line released 2 days ago, reallocated
        # today. Uses large time gap so released_at >> allocated_at in DB.
        start_of_today = timezone.make_aware(
            datetime.combine(self.today, time.min)
        )
        _make_allocation(
            self.employee, self.line,
            allocated_at=start_of_today - timedelta(days=2),
            released_at=start_of_today - timedelta(hours=1),
        )
        _make_allocation(
            self.employee, self.line,
            allocated_at=start_of_today + timedelta(hours=1),
        )

        # Pendency-based: different employee, resolved via AllocationPendency
        second_employee = _make_employee(email="s2@corp.com", eid="E04")
        second_line = _make_line(number="+5511999990004")
        second_alloc = _make_allocation(second_employee, second_line)
        AllocationPendency.objects.create(
            employee=second_employee,
            allocation=second_alloc,
            action=AllocationPendency.ActionType.NO_ACTION,
            last_submitted_action=(
                AllocationPendency.ActionType.RECONNECT_WHATSAPP
            ),
            resolved_at=timezone.now(),
        )

        result = build_reconnected_numbers_for_day(self.today)
        numbers = {r["numero"] for r in result}
        self.assertIn(self.line.phone_number, numbers)        # ORM-based
        self.assertIn(second_line.phone_number, numbers)      # Pendency-based
        self.assertEqual(len(result), 2)
