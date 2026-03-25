from __future__ import annotations

import math
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from django.db import close_old_connections

from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import WhatsAppSession
from whatsapp.services.session_service import WhatsAppSessionService


@dataclass(frozen=True)
class WhatsAppLoadTestInstanceSummary:
    instance_name: str
    total_requests: int
    success_count: int
    failure_count: int


@dataclass(frozen=True)
class WhatsAppLoadTestRequestResult:
    session_id: str
    instance_name: str
    success: bool
    latency_ms: int
    detail: str


@dataclass(frozen=True)
class WhatsAppLoadTestSummary:
    scenario: str
    label: str
    selected_sessions: int
    concurrency: int
    success_count: int
    failure_count: int
    average_latency_ms: int | None
    p95_latency_ms: int | None
    instance_summaries: list[WhatsAppLoadTestInstanceSummary]
    failures: list[WhatsAppLoadTestRequestResult]


class WhatsAppLoadTestService:
    SCENARIO_LABELS = {
        "client_get_session": "Leitura remota via MeowClient.get_session",
        "client_get_qr": "Leitura remota via MeowClient.get_qr",
        "client_connect_session": "Escrita remota via MeowClient.connect_session",
        "service_get_status": "Status ponta a ponta via WhatsAppSessionService.get_status",
        "service_get_qr": "QR ponta a ponta via WhatsAppSessionService.get_qr",
    }

    def list_scenarios(self) -> dict[str, str]:
        return dict(self.SCENARIO_LABELS)

    def run(
        self,
        *,
        scenario: str,
        queryset=None,
        session_limit: int | None = None,
        concurrency: int = 10,
        min_sessions: int = 0,
        connected_only: bool = False,
    ) -> WhatsAppLoadTestSummary:
        runner = self._get_runner(scenario)
        queryset = queryset if queryset is not None else WhatsAppSession.objects.all()
        queryset = queryset.select_related("line", "meow_instance").filter(
            is_active=True
        )
        if connected_only:
            queryset = queryset.filter(status="CONNECTED")

        ordered_queryset = queryset.order_by("session_id")
        sessions = (
            list(ordered_queryset[:session_limit])
            if session_limit
            else list(ordered_queryset)
        )

        if min_sessions and len(sessions) < min_sessions:
            raise ValueError(
                f"Sessoes insuficientes para o teste: "
                f"{len(sessions)} encontradas, minimo exigido {min_sessions}."
            )
        if not sessions:
            raise ValueError("Nenhuma sessao elegivel para o teste de carga.")

        worker_count = min(max(1, concurrency), len(sessions))
        request_results: list[WhatsAppLoadTestRequestResult] = []
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self._run_single_request, runner, session): session
                for session in sessions
            }
            for future in as_completed(future_map):
                request_results.append(future.result())

        return self._build_summary(
            scenario=scenario,
            selected_sessions=len(sessions),
            concurrency=worker_count,
            request_results=request_results,
        )

    def _get_runner(self, scenario: str):
        if scenario == "client_get_session":
            return self._run_client_get_session
        if scenario == "client_get_qr":
            return self._run_client_get_qr
        if scenario == "client_connect_session":
            return self._run_client_connect_session
        if scenario == "service_get_status":
            return self._run_service_get_status
        if scenario == "service_get_qr":
            return self._run_service_get_qr
        raise ValueError(
            f"Cenario de carga invalido: {scenario}. "
            f"Use um dos cenarios suportados: "
            f"{', '.join(sorted(self.SCENARIO_LABELS))}."
        )

    def _run_single_request(
        self,
        runner,
        session: WhatsAppSession,
    ) -> WhatsAppLoadTestRequestResult:
        close_old_connections()
        started_at = time.monotonic()
        try:
            detail = runner(session)
            success = True
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            success = False
        finally:
            close_old_connections()

        latency_ms = max(0, int(round((time.monotonic() - started_at) * 1000)))
        return WhatsAppLoadTestRequestResult(
            session_id=session.session_id,
            instance_name=session.meow_instance.name,
            success=success,
            latency_ms=latency_ms,
            detail=detail,
        )

    def _build_summary(
        self,
        *,
        scenario: str,
        selected_sessions: int,
        concurrency: int,
        request_results: list[WhatsAppLoadTestRequestResult],
    ) -> WhatsAppLoadTestSummary:
        latencies = [result.latency_ms for result in request_results]
        success_count = sum(result.success for result in request_results)
        failure_count = len(request_results) - success_count
        average_latency_ms = (
            int(round(sum(latencies) / len(latencies))) if latencies else None
        )
        p95_latency_ms = self._percentile_ms(latencies, percentile=0.95)

        by_instance: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "success": 0, "failure": 0}
        )
        for result in request_results:
            stats = by_instance[result.instance_name]
            stats["total"] += 1
            if result.success:
                stats["success"] += 1
            else:
                stats["failure"] += 1

        instance_summaries = [
            WhatsAppLoadTestInstanceSummary(
                instance_name=instance_name,
                total_requests=stats["total"],
                success_count=stats["success"],
                failure_count=stats["failure"],
            )
            for instance_name, stats in sorted(by_instance.items())
        ]
        failures = [result for result in request_results if not result.success]

        return WhatsAppLoadTestSummary(
            scenario=scenario,
            label=self.SCENARIO_LABELS[scenario],
            selected_sessions=selected_sessions,
            concurrency=concurrency,
            success_count=success_count,
            failure_count=failure_count,
            average_latency_ms=average_latency_ms,
            p95_latency_ms=p95_latency_ms,
            instance_summaries=instance_summaries,
            failures=failures,
        )

    @staticmethod
    def _percentile_ms(latencies: list[int], *, percentile: float) -> int | None:
        if not latencies:
            return None

        ordered = sorted(latencies)
        rank = max(1, math.ceil(len(ordered) * percentile))
        return ordered[rank - 1]

    @staticmethod
    def _run_client_get_session(session: WhatsAppSession) -> str:
        client = MeowClient(session.meow_instance.base_url)
        payload = client.get_session(session.session_id)
        return f"status={payload.get('status', '-')}"

    @staticmethod
    def _run_client_get_qr(session: WhatsAppSession) -> str:
        client = MeowClient(session.meow_instance.base_url)
        payload = client.get_qr(session.session_id)
        return (
            f"has_qr={bool(payload.get('has_qr'))} "
            f"connected={bool(payload.get('connected'))}"
        )

    @staticmethod
    def _run_client_connect_session(session: WhatsAppSession) -> str:
        client = MeowClient(session.meow_instance.base_url)
        payload = client.connect_session(session.session_id)
        return f"status={payload.get('status', '-')}"

    @staticmethod
    def _run_service_get_status(session: WhatsAppSession) -> str:
        result = WhatsAppSessionService().get_status(session.line)
        return f"status={result.status}"

    @staticmethod
    def _run_service_get_qr(session: WhatsAppSession) -> str:
        result = WhatsAppSessionService().get_qr(session.line)
        return f"status={result.status} has_qr={result.has_qr}"
