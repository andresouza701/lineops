from django.core.management.base import BaseCommand

from core.normalization import (
    collapse_whitespace,
    normalize_carrier_name,
    normalize_email_address,
    normalize_full_name,
    normalize_portfolio_value,
    normalize_unit_value,
)
from employees.models import Employee
from telecom.models import SIMcard


class Command(BaseCommand):
    help = (
        "Normaliza nomes, emails, carteira, unidade e operadora. "
        "Padrao: dry-run; use --apply para persistir."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persiste as mudancas normalizadas no banco.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        mode_label = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(f"[{mode_label}] Auditoria de normalizacao iniciada.")

        employee_updates, employee_skips = self._normalize_employees(
            apply_changes=apply_changes
        )
        simcard_updates = self._normalize_simcards(apply_changes=apply_changes)

        self.stdout.write(
            self.style.SUCCESS(
                "Normalizacao concluida: "
                f"employees atualizados={employee_updates}, "
                f"employees ignorados={employee_skips}, "
                f"simcards atualizados={simcard_updates}."
            )
        )

    def _normalize_employees(self, *, apply_changes: bool):
        updates = 0
        skips = 0

        for employee in Employee.all_objects.all().order_by("pk"):
            normalized_fields = {
                "full_name": normalize_full_name(employee.full_name),
                "corporate_email": normalize_email_address(employee.corporate_email),
                "manager_email": normalize_email_address(employee.manager_email) or None,
                "employee_id": normalize_portfolio_value(employee.employee_id),
                "teams": normalize_unit_value(employee.teams),
                "pa": collapse_whitespace(employee.pa) or None,
            }
            changed_fields = {
                field_name: value
                for field_name, value in normalized_fields.items()
                if getattr(employee, field_name) != value
            }
            if not changed_fields:
                continue

            if (
                not employee.is_deleted
                and "full_name" in changed_fields
                and Employee.has_active_full_name_conflict(
                    changed_fields["full_name"],
                    exclude_id=employee.pk,
                )
            ):
                skips += 1
                self.stdout.write(
                    self.style.WARNING(
                        "Employee ignorado por colisao de nome normalizado: "
                        f"id={employee.pk} "
                        f"'{employee.full_name}' -> '{changed_fields['full_name']}'"
                    )
                )
                continue

            self.stdout.write(
                f"Employee id={employee.pk}: {self._format_changes(changed_fields)}"
            )
            if apply_changes:
                for field_name, value in changed_fields.items():
                    setattr(employee, field_name, value)
                employee.save(update_fields=[*changed_fields.keys(), "updated_at"])
            updates += 1

        return updates, skips

    def _normalize_simcards(self, *, apply_changes: bool):
        updates = 0

        for simcard in SIMcard.all_objects.all().order_by("pk"):
            normalized_carrier = normalize_carrier_name(simcard.carrier)
            if simcard.carrier == normalized_carrier:
                continue

            changed_fields = {"carrier": normalized_carrier}
            self.stdout.write(
                f"SIMcard id={simcard.pk}: {self._format_changes(changed_fields)}"
            )
            if apply_changes:
                simcard.carrier = normalized_carrier
                simcard.save(update_fields=["carrier", "updated_at"])
            updates += 1

        return updates

    @staticmethod
    def _format_changes(changed_fields):
        return ", ".join(
            f"{field_name}='{value}'" for field_name, value in changed_fields.items()
        )
