from __future__ import annotations

import threading
import time
import unittest
from datetime import timedelta
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from telecom.models import PhoneLine, SIMcard
from users.models import SystemUser
from whatsapp.choices import (
    WhatsAppIntegrationJobStatus,
    WhatsAppIntegrationJobType,
    WhatsAppSessionStatus,
)
from whatsapp.clients.meow_client import MeowClient
from whatsapp.models import MeowInstance, WhatsAppIntegrationJob, WhatsAppSession
from whatsapp.services.integration_job_service import WhatsAppIntegrationJobService
from whatsapp.services.session_service import (
    WhatsAppSessionResult,
    WhatsAppSessionService,
)
from whatsapp.services.worker_service import WhatsAppIntegrationWorkerService


POSTGRES_ONLY = unittest.skipUnless(
    connection.vendor == "postgresql",
    "Requer banco de teste PostgreSQL.",
)


@POSTGRES_ONLY
class WhatsAppPostgresCriticalPathTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = SystemUser.objects.create_user(
            email="admin-whatsapp-postgres@test.com",
            password="123456",
            role=SystemUser.Role.ADMIN,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.meow = MeowInstance.objects.create(
            name="Postgres Meow",
            base_url="http://postgres-meow.local",
        )
        self.sim = SIMcard.objects.create(
            iccid="89000000000000777001",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        self.line = PhoneLine.objects.create(
            phone_number="+5511999997701",
            sim_card=self.sim,
            status=PhoneLine.Status.AVAILABLE,
        )

    def _threaded_call(self, target, *args):
        errors: list[str] = []
        values: list[object] = []
        barrier = threading.Barrier(len(args) + 1)

        def runner(worker_arg):
            close_old_connections()
            try:
                barrier.wait()
                values.append(target(worker_arg))
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=runner, args=(worker_arg,))
            for worker_arg in args
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        return values, errors

    def test_get_or_create_session_is_idempotent_under_parallel_requests(self):
        def create_session(_worker_code):
            service = WhatsAppSessionService()
            return service.get_or_create_session(self.line).pk

        with patch(
            "whatsapp.services.session_service.InstanceSelectorService.select_available_instance",
            return_value=self.meow,
        ):
            values, errors = self._threaded_call(
                create_session,
                "worker-a",
                "worker-b",
            )

        self.assertEqual(errors, [])
        self.assertEqual(len(values), 2)
        self.assertEqual(len(set(values)), 1)
        self.assertEqual(WhatsAppSession.objects.filter(line=self.line).count(), 1)

    def test_single_claim_wins_for_same_due_job(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999997701",
            status=WhatsAppSessionStatus.NEW,
        )
        job, _ = WhatsAppIntegrationJobService().enqueue(
            session=session,
            job_type=WhatsAppIntegrationJobType.CREATE_SESSION,
            correlation_id="pg-claim-001",
            request_payload={"session_id": session.session_id},
        )

        def claim_job(worker_code):
            service = WhatsAppIntegrationJobService()
            claimed = service.claim_due_jobs(worker_code=worker_code, limit=1)
            return [item.pk for item in claimed]

        values, errors = self._threaded_call(
            claim_job,
            "worker-a",
            "worker-b",
        )

        self.assertEqual(errors, [])
        claimed_total = sum(len(item) for item in values)
        self.assertEqual(claimed_total, 1)
        job.refresh_from_db()
        self.assertEqual(job.status, WhatsAppIntegrationJobStatus.RUNNING)
        self.assertIn(job.claimed_by, {"worker-a", "worker-b"})

    def test_parallel_session_creation_does_not_exceed_instance_max_capacity(self):
        self.meow.warning_sessions = 1
        self.meow.max_sessions = 1
        self.meow.save(update_fields=["warning_sessions", "max_sessions", "updated_at"])

        other_sim = SIMcard.objects.create(
            iccid="89000000000000777002",
            carrier="Carrier A",
            status=SIMcard.Status.AVAILABLE,
        )
        other_line = PhoneLine.objects.create(
            phone_number="+5511999997702",
            sim_card=other_sim,
            status=PhoneLine.Status.AVAILABLE,
        )

        def create_session(line_pk):
            service = WhatsAppSessionService()
            line = PhoneLine.objects.get(pk=line_pk)
            return service.get_or_create_session(line).pk

        values, errors = self._threaded_call(
            create_session,
            self.line.pk,
            other_line.pk,
        )

        self.assertEqual(len(values), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Nenhuma instancia Meow ativa e com capacidade disponivel.", errors[0])
        self.assertEqual(WhatsAppSession.objects.filter(meow_instance=self.meow).count(), 1)

    def test_parallel_workers_do_not_process_same_job_twice(self):
        session = WhatsAppSession.objects.create(
            line=self.line,
            meow_instance=self.meow,
            session_id="session_+5511999997701",
            status=WhatsAppSessionStatus.NEW,
        )
        job, _ = WhatsAppIntegrationJobService().enqueue(
            session=session,
            job_type=WhatsAppIntegrationJobType.CREATE_SESSION,
            correlation_id="pg-worker-001",
            request_payload={"session_id": session.session_id},
        )
        processed: list[str] = []
        processed_lock = threading.Lock()

        def fake_connect(service_self, line, *, correlation_id=""):
            time.sleep(0.1)
            current_session = WhatsAppSession.objects.get(line=line)
            with processed_lock:
                processed.append(correlation_id)
            return WhatsAppSessionResult(
                session=current_session,
                status=WhatsAppSessionStatus.CONNECTED,
                remote_payload={"details": {"connected": True}},
                connected=True,
                correlation_id=correlation_id,
            )

        def run_worker(worker_code):
            return WhatsAppIntegrationWorkerService().run_once(worker_code=worker_code, limit=1)

        with patch.object(WhatsAppSessionService, "connect", fake_connect):
            values, errors = self._threaded_call(
                run_worker,
                "worker-a",
                "worker-b",
            )

        self.assertEqual(errors, [])
        self.assertEqual(processed, ["pg-worker-001"])
        self.assertEqual(sum(item.processed_jobs for item in values), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, WhatsAppIntegrationJobStatus.SUCCESS)

    def test_api_and_worker_flow_converges_on_postgres(self):
        create_response = self.client.post(
            reverse("whatsapp_api:list_create"),
            data={"line_id": self.line.pk},
            format="json",
            HTTP_X_CORRELATION_ID="pg-e2e-001",
        )
        self.assertEqual(create_response.status_code, 201)
        session_id = create_response.json()["id"]
        session = WhatsAppSession.objects.get(pk=session_id)

        qr_expires = int((timezone.now() + timedelta(minutes=1)).timestamp())
        with patch.object(
            MeowClient,
            "create_session",
            return_value={"details": {"connected": False, "hasQR": False}},
        ):
            first_summary = WhatsAppIntegrationWorkerService().run_once(
                worker_code="pg-worker-create",
                limit=1,
            )
        self.assertEqual(first_summary.processed_jobs, 1)
        WhatsAppIntegrationJob.objects.filter(
            session=session,
            job_type=WhatsAppIntegrationJobType.SYNC_STATUS,
            status=WhatsAppIntegrationJobStatus.PENDING,
        ).update(available_at=timezone.now())

        with patch.object(
            MeowClient,
            "get_session",
            return_value={
                "details": {
                    "connected": False,
                    "hasQR": True,
                    "qrCode": "base64-postgres-qr",
                    "qrExpires": qr_expires,
                }
            },
        ):
            second_summary = WhatsAppIntegrationWorkerService().run_once(
                worker_code="pg-worker-sync",
                limit=1,
            )
        self.assertEqual(second_summary.processed_jobs, 1)

        status_response = self.client.get(
            reverse("whatsapp_api:status", args=[session.pk]),
            HTTP_X_CORRELATION_ID="pg-e2e-status",
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(
            status_response.json()["status"],
            WhatsAppSessionStatus.QR_AVAILABLE,
        )

        qr_response = self.client.post(
            reverse("whatsapp_api:generate_qr", args=[session.pk]),
            data={},
            format="json",
            HTTP_X_CORRELATION_ID="pg-e2e-qr",
        )
        self.assertEqual(qr_response.status_code, 200)
        self.assertEqual(qr_response.json()["qr_code"], "base64-postgres-qr")

        WhatsAppIntegrationJob.objects.filter(
            session=session,
            job_type=WhatsAppIntegrationJobType.SYNC_STATUS,
            status=WhatsAppIntegrationJobStatus.PENDING,
        ).update(available_at=timezone.now() + timedelta(hours=1))

        delete_response = self.client.delete(
            reverse("whatsapp_api:delete_session", args=[session.pk]),
            HTTP_X_CORRELATION_ID="pg-e2e-delete",
        )
        self.assertEqual(delete_response.status_code, 202)

        with patch.object(
            MeowClient,
            "disconnect_session",
            return_value={"success": True},
        ):
            third_summary = WhatsAppIntegrationWorkerService().run_once(
                worker_code="pg-worker-delete",
                limit=1,
            )
        self.assertEqual(third_summary.processed_jobs, 1)

        session.refresh_from_db()
        self.assertEqual(session.status, WhatsAppSessionStatus.DISCONNECTED)
        self.assertGreaterEqual(
            WhatsAppIntegrationJob.objects.filter(
                session=session,
                correlation_id="pg-e2e-001",
            ).count(),
            2,
        )
