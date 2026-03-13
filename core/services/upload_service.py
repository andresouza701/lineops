from __future__ import annotations

import csv
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils.text import slugify

from employees.models import Employee
from telecom.models import PhoneLine, SIMcard

logger = logging.getLogger(__name__)

DUPLICATE_EMPLOYEE_NAME_MESSAGE = "Ja existe um usuario cadastrado com este nome."


@dataclass
class UploadSummary:
    rows_processed: int = 0
    employees_created: int = 0
    employees_updated: int = 0
    simcards_created: int = 0
    simcards_updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict[str, int | list[str]]:
        return {
            "rows_processed": self.rows_processed,
            "employees_created": self.employees_created,
            "employees_updated": self.employees_updated,
            "simcards_created": self.simcards_created,
            "simcards_updated": self.simcards_updated,
            "errors": self.errors,
        }


ALLOWED_EMPLOYEE_STATUSES = {value.lower(): value for value in Employee.Status.values}
ALLOWED_SIM_STATUSES = {value.lower(): value for value in SIMcard.Status.values}

EMPLOYEE_STATUS_ALIASES = {
    "ativo": Employee.Status.ACTIVE,
    "inativo": Employee.Status.INACTIVE,
}

SIM_STATUS_ALIASES = {
    "disponivel": SIMcard.Status.AVAILABLE,
    "ativo": SIMcard.Status.ACTIVE,
    "bloqueado": SIMcard.Status.BLOCKED,
    "cancelado": SIMcard.Status.CANCELLED,
}


def process_upload_file(file_path: Path) -> UploadSummary:
    extension = file_path.suffix.lower()
    if extension == ".csv":
        rows = _parse_csv(file_path)
    elif extension == ".xlsx":
        rows = _parse_xlsx(file_path)
    else:
        raise ValueError("Formato de arquivo não suportado: use CSV ou XLSX.")

    return _ingest_rows(rows)


def _parse_csv(file_path: Path) -> list[dict[str, str]]:
    with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        sample = csv_file.read(2048)
        csv_file.seek(0)

        delimiter = ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
            delimiter = dialect.delimiter
        except csv.Error:
            if sample.count(";") > sample.count(","):
                delimiter = ";"

        reader = csv.DictReader(csv_file, delimiter=delimiter)
        return [_normalize_row(row) for row in reader]


def _parse_xlsx(file_path: Path) -> list[dict[str, str]]:
    try:
        from openpyxl import load_workbook
    except ModuleNotFoundError as exc:
        raise ValueError(
            "Processamento XLSX indisponível: instale a dependência openpyxl."
        ) from exc

    workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    try:
        headers = [str(cell or "").strip().lower() for cell in next(rows)]
    except StopIteration:  # empty file
        return []

    normalized_rows = []
    for row in rows:
        values = {
            headers[idx]: (row[idx] if idx < len(row) else "")
            for idx in range(len(headers))
        }
        normalized_rows.append(_normalize_row(values))
    return normalized_rows


def _normalize_row(row: dict[str, object]) -> dict[str, str]:
    return {
        key.strip().lower(): _stringify(value)
        for key, value in row.items()
        if key is not None
    }


def _stringify(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _ingest_rows(rows: Iterable[dict[str, str]]) -> UploadSummary:
    summary = UploadSummary()

    for index, raw in enumerate(rows, start=2):
        if not any(raw.values()):
            continue

        try:
            # Isola cada linha em uma transação para evitar persistência parcial.
            with transaction.atomic():
                kind = raw.get("type", "").lower()
                if kind == "employee":
                    _upsert_employee(raw, summary)
                elif kind == "simcard":
                    _upsert_simcard(raw, summary)
                else:
                    raise ValueError("Coluna 'type' deve ser 'employee' ou 'simcard'.")
            summary.rows_processed += 1
        except (ValueError, IntegrityError) as exc:
            summary.errors.append(f"Linha {index}: {exc}")
        except Exception:
            logger.exception(
                "Unexpected failure while processing upload row",
                extra={"row_index": index},
            )
            raise

    return summary


def _upsert_employee(row: dict[str, str], summary: UploadSummary) -> None:
    required = ["full_name", "corporate_email", "employee_id"]
    _ensure_required(row, required)
    teams = row.get("teams") or row.get("team") or row.get("department")
    if not teams:
        raise ValueError("Coluna obrigatÃ³ria ausente ou vazia: teams.")

    status = _normalize_employee_status(row.get("status"))
    full_name = row["full_name"]
    employee_id = row["employee_id"]

    duplicate_name_exists = (
        Employee.all_objects.filter(
            full_name__iexact=full_name,
            is_deleted=False,
        )
        .exclude(employee_id=employee_id)
        .exists()
    )
    if duplicate_name_exists:
        raise ValueError(DUPLICATE_EMPLOYEE_NAME_MESSAGE)

    defaults = {
        "full_name": full_name,
        "corporate_email": row["corporate_email"],
        "teams": teams,
        "status": status,
        "is_deleted": False,
    }

    employee, created = Employee.all_objects.update_or_create(
        employee_id=employee_id,
        defaults=defaults,
    )
    if created:
        summary.employees_created += 1
    else:
        summary.employees_updated += 1


def _upsert_simcard(row: dict[str, str], summary: UploadSummary) -> None:
    required = ["iccid", "carrier"]
    _ensure_required(row, required)

    status = _normalize_sim_status(row.get("status"))
    defaults = {
        "carrier": row["carrier"],
        "status": status,
        "is_deleted": False,
    }

    simcard = SIMcard.all_objects.filter(iccid=row["iccid"]).order_by("-id").first()
    if simcard is None:
        simcard = SIMcard.objects.create(iccid=row["iccid"], **defaults)
        summary.simcards_created += 1
    else:
        for field_name, value in defaults.items():
            setattr(simcard, field_name, value)
        simcard.save(update_fields=[*defaults.keys(), "updated_at"])
        summary.simcards_updated += 1

    phone_number = row.get("phone_number") or ""
    if phone_number:
        PhoneLine.objects.update_or_create(
            phone_number=phone_number,
            defaults={
                "sim_card": simcard,
                "status": PhoneLine.Status.AVAILABLE,
                "is_deleted": False,
            },
        )


def _ensure_required(row: dict[str, str], required_fields: list[str]) -> None:
    missing = [field for field in required_fields if not row.get(field)]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Colunas obrigatórias ausentes ou vazias: {joined}.")


def _normalize_employee_status(raw_status: str | None) -> str:
    if not raw_status:
        return Employee.Status.INACTIVE

    normalized = slugify(raw_status).replace("-", "").lower()
    if normalized in EMPLOYEE_STATUS_ALIASES:
        return EMPLOYEE_STATUS_ALIASES[normalized]

    status = ALLOWED_EMPLOYEE_STATUSES.get(normalized)
    if not status:
        raise ValueError(
            "Status de usuário inválido. "
            "Use 'active'/'inactive' ou 'ativo'/'inativo'."
        )
    return status


def _normalize_sim_status(raw_status: str | None) -> str:
    if not raw_status:
        return SIMcard.Status.AVAILABLE

    normalized = slugify(raw_status).replace("-", "").lower()
    if normalized in SIM_STATUS_ALIASES:
        return SIM_STATUS_ALIASES[normalized]

    status = ALLOWED_SIM_STATUSES.get(normalized)
    if not status:
        raise ValueError(
            "Status de SIMcard inválido. "
            "Use AVAILABLE/ACTIVE/BLOCKED/CANCELLED ou equivalentes em português."
        )
    return status
