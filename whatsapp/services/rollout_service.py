from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db.models import QuerySet

from whatsapp.models import MeowInstance
from whatsapp.services.capacity_service import MeowCapacityService


@dataclass(frozen=True)
class MeowRolloutStage:
    stage_sessions: int
    target_sessions: int
    warning_sessions: int
    max_sessions: int


@dataclass
class MeowRolloutSummary:
    stages: list[MeowRolloutStage]
    active_instances: int
    total_active_sessions: int
    current_capacity_sessions: int
    final_capacity_sessions: int
    expected_active_instances: int
    configured_warning_sessions: list[int]
    current_stage: MeowRolloutStage | None
    next_stage: MeowRolloutStage | None
    is_uniform: bool
    should_open_sixth_meow: bool
    sixth_meow_trigger_sessions: int
    recommendation: str


class MeowRolloutService:
    DEFAULT_STAGES = (25, 30, 35, 40)
    DEFAULT_BUFFER = 5
    DEFAULT_OPERATIONAL_CEILING = 45
    DEFAULT_EXPECTED_ACTIVE_INSTANCES = 5

    def list_stages(self) -> list[MeowRolloutStage]:
        stage_values = self._get_stage_values()
        buffer = self._get_rollout_buffer()
        operational_ceiling = self._get_operational_ceiling()

        stages = []
        for stage_sessions in stage_values:
            target_sessions = max(stage_sessions - buffer, 1)
            max_sessions = min(stage_sessions + buffer, operational_ceiling)
            if max_sessions < stage_sessions:
                max_sessions = stage_sessions
            stages.append(
                MeowRolloutStage(
                    stage_sessions=stage_sessions,
                    target_sessions=target_sessions,
                    warning_sessions=stage_sessions,
                    max_sessions=max_sessions,
                )
            )
        return stages

    def get_stage(self, stage_sessions: int) -> MeowRolloutStage:
        for stage in self.list_stages():
            if stage.stage_sessions == int(stage_sessions):
                return stage
        configured = ", ".join(str(value) for value in self._get_stage_values())
        raise ValueError(
            f"Etapa invalida: {stage_sessions}. Use uma das etapas configuradas: "
            f"{configured}."
        )

    def apply_stage(
        self,
        stage_sessions: int,
        *,
        queryset: QuerySet | None = None,
        dry_run: bool = False,
    ) -> list[MeowInstance]:
        stage = self.get_stage(stage_sessions)
        queryset = queryset if queryset is not None else MeowInstance.objects.all()
        instances = list(queryset.order_by("name"))

        for instance in instances:
            instance.target_sessions = stage.target_sessions
            instance.warning_sessions = stage.warning_sessions
            instance.max_sessions = stage.max_sessions
            instance.full_clean()
            if not dry_run:
                instance.save(
                    update_fields=[
                        "target_sessions",
                        "warning_sessions",
                        "max_sessions",
                        "updated_at",
                    ]
                )
        return instances

    def build_summary(
        self,
        *,
        queryset: QuerySet | None = None,
        include_inactive: bool = False,
    ) -> MeowRolloutSummary:
        queryset = queryset if queryset is not None else MeowInstance.objects.all()
        capacity_summaries = MeowCapacityService().summarize_instances(
            queryset=queryset,
            include_inactive=include_inactive,
        )
        stages = self.list_stages()
        stage_map = {stage.stage_sessions: stage for stage in stages}
        instances = [summary.instance for summary in capacity_summaries]
        configured_profiles = {
            (
                instance.target_sessions,
                instance.warning_sessions,
                instance.max_sessions,
            )
            for instance in instances
        }
        configured_warning_sessions = sorted(
            {instance.warning_sessions for instance in instances}
        )
        is_uniform = len(configured_profiles) <= 1
        current_stage = None
        if is_uniform and len(configured_warning_sessions) == 1:
            candidate_stage = stage_map.get(configured_warning_sessions[0])
            if candidate_stage is not None and configured_profiles == {
                (
                    candidate_stage.target_sessions,
                    candidate_stage.warning_sessions,
                    candidate_stage.max_sessions,
                )
            }:
                current_stage = candidate_stage

        next_stage = None
        if current_stage is not None:
            next_stage = next(
                (
                    stage
                    for stage in stages
                    if stage.stage_sessions > current_stage.stage_sessions
                ),
                None,
            )

        active_instances = len(capacity_summaries)
        total_active_sessions = sum(
            summary.active_sessions for summary in capacity_summaries
        )
        current_capacity_sessions = sum(
            instance.warning_sessions for instance in instances
        )
        expected_active_instances = int(
            getattr(
                settings,
                "WHATSAPP_MEOW_EXPECTED_ACTIVE_INSTANCES",
                self.DEFAULT_EXPECTED_ACTIVE_INSTANCES,
            )
        )
        final_capacity_sessions = expected_active_instances * stages[-1].stage_sessions
        should_open_sixth_meow = (
            current_stage == stages[-1]
            and active_instances >= expected_active_instances
            and total_active_sessions >= final_capacity_sessions
        )

        return MeowRolloutSummary(
            stages=stages,
            active_instances=active_instances,
            total_active_sessions=total_active_sessions,
            current_capacity_sessions=current_capacity_sessions,
            final_capacity_sessions=final_capacity_sessions,
            expected_active_instances=expected_active_instances,
            configured_warning_sessions=configured_warning_sessions,
            current_stage=current_stage,
            next_stage=next_stage,
            is_uniform=is_uniform,
            should_open_sixth_meow=should_open_sixth_meow,
            sixth_meow_trigger_sessions=final_capacity_sessions,
            recommendation=self._build_recommendation(
                active_instances=active_instances,
                current_stage=current_stage,
                next_stage=next_stage,
                is_uniform=is_uniform,
                should_open_sixth_meow=should_open_sixth_meow,
                total_active_sessions=total_active_sessions,
                trigger_sessions=final_capacity_sessions,
            ),
        )

    def _build_recommendation(
        self,
        *,
        active_instances: int,
        current_stage: MeowRolloutStage | None,
        next_stage: MeowRolloutStage | None,
        is_uniform: bool,
        should_open_sixth_meow: bool,
        total_active_sessions: int,
        trigger_sessions: int,
    ) -> str:
        if active_instances == 0:
            return "Nenhuma instancia ativa para avaliar rollout operacional."
        if not is_uniform:
            return (
                "Padronize target, warning e max das instancias antes de avancar "
                "o rollout."
            )
        if current_stage is None:
            return (
                "A configuracao atual das instancias nao corresponde as etapas "
                "padrao do rollout."
            )
        if should_open_sixth_meow:
            return (
                f"Abrir o 6o Meow: {total_active_sessions} sessoes ativas "
                f"atingiram o gatilho de {trigger_sessions} na etapa final."
            )
        if next_stage is not None:
            return (
                f"Etapa atual liberada em {current_stage.stage_sessions} "
                f"sessoes por instancia. Proxima etapa: "
                f"{next_stage.stage_sessions}."
            )
        return (
            f"Etapa final em operacao. Abrir o 6o Meow ao atingir "
            f"{trigger_sessions} sessoes ativas."
        )

    def _get_stage_values(self) -> list[int]:
        raw_values = getattr(
            settings,
            "WHATSAPP_MEOW_ROLLOUT_STAGES",
            self.DEFAULT_STAGES,
        )
        values = sorted({int(value) for value in raw_values})
        if not values:
            raise ValueError("WHATSAPP_MEOW_ROLLOUT_STAGES precisa conter etapas.")
        return values

    def _get_rollout_buffer(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_MEOW_ROLLOUT_BUFFER",
                self.DEFAULT_BUFFER,
            )
        )

    def _get_operational_ceiling(self) -> int:
        return int(
            getattr(
                settings,
                "WHATSAPP_MEOW_OPERATIONAL_CEILING",
                self.DEFAULT_OPERATIONAL_CEILING,
            )
        )
