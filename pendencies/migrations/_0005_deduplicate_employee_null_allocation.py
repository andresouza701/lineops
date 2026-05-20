"""
Deduplication logic extracted into its own importable module so tests can call
the function directly without executing the migration runner.
"""

from django.db.models import Q


def deduplicate_employee_null_pendencies(apps, schema_editor):
    """
    For each employee that has more than one AllocationPendency with
    allocation_id IS NULL, keep one canonical row and delete the rest.

    Canonical selection priority (spec order):
      1. action != 'no_action'  (open pendency)
      2. technical_responsible_id IS NOT NULL
      3. highest updated_at
      4. highest id

    Merge rules applied before deletion:
      observation          - keep canonical if non-empty; else newest non-empty duplicate
      technical_responsible- keep canonical if set; else newest duplicate
      last_submitted_action- keep canonical if set; else newest duplicate
      pendency_submitted_at- keep earliest non-null among open duplicates
      resolved_at          - keep canonical if set; else newest duplicate
      last_action_changed_at - keep newest non-null
      updated_by           - keep canonical if set; else newest duplicate
    """
    AllocationPendency = apps.get_model("pendencies", "AllocationPendency")

    # Find employees with duplicates
    from django.db.models import Count

    duplicated_employees = (
        AllocationPendency.objects.filter(allocation_id__isnull=True)
        .values("employee_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .values_list("employee_id", flat=True)
    )

    for employee_id in duplicated_employees:
        rows = list(
            AllocationPendency.objects.filter(
                employee_id=employee_id,
                allocation_id__isnull=True,
            ).order_by(
                # open first (no_action sorts last in ASC, so we sort open rows first)
                "action",  # alphabetically "no_action" > "new_number"/"pending"/"reconnect_whatsapp" — not reliable
                "-updated_at",
                "-id",
            )
        )

        def _priority(row):
            return (
                0 if row.action != "no_action" else 1,
                0 if row.technical_responsible_id is not None else 1,
                # negate timestamps for descending sort via tuple comparison
                -(row.updated_at.timestamp() if row.updated_at else 0),
                -row.id,
            )

        rows.sort(key=_priority)
        canonical = rows[0]
        duplicates = rows[1:]

        # Merge fields from duplicates into canonical
        for dup in duplicates:
            if not canonical.observation and dup.observation:
                canonical.observation = dup.observation
            if not canonical.technical_responsible_id and dup.technical_responsible_id:
                canonical.technical_responsible_id = dup.technical_responsible_id
            if not canonical.last_submitted_action and dup.last_submitted_action:
                canonical.last_submitted_action = dup.last_submitted_action
            if not canonical.updated_by_id and dup.updated_by_id:
                canonical.updated_by_id = dup.updated_by_id
            if not canonical.resolved_at and dup.resolved_at:
                canonical.resolved_at = dup.resolved_at

            # pendency_submitted_at: keep earliest non-null among open rows
            if dup.action != "no_action" and dup.pendency_submitted_at:
                if canonical.pendency_submitted_at is None:
                    canonical.pendency_submitted_at = dup.pendency_submitted_at
                elif dup.pendency_submitted_at < canonical.pendency_submitted_at:
                    canonical.pendency_submitted_at = dup.pendency_submitted_at

            # last_action_changed_at: keep newest non-null
            if dup.last_action_changed_at:
                if canonical.last_action_changed_at is None:
                    canonical.last_action_changed_at = dup.last_action_changed_at
                elif dup.last_action_changed_at > canonical.last_action_changed_at:
                    canonical.last_action_changed_at = dup.last_action_changed_at

        canonical.save()

        dup_ids = [d.id for d in duplicates]
        deleted, _ = AllocationPendency.objects.filter(id__in=dup_ids).delete()
        print(
            f"\n  Employee {employee_id}: kept pk={canonical.pk}, "
            f"deleted {deleted} duplicate(s)."
        )
