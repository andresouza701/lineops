"""SVI-07 — achado de concorrencia no indicador de selo do Django Admin
(BlipConfigurationAdmin, I26), fortalecido na checagem focada pre-commit.

Fonte da verdade: docs/superpowers/specs/2026-10-05-phone-line-seal-
indicator-design.md.

Alcance explicito: estes testes chamam `get_queryset`/`phone_number_display`
DIRETAMENTE na instancia registrada de ModelAdmin (mesmo padrao de
telecom/tests.py, que chama `admin.site._registry[Model].get_form(request)`
sem HTTP) — nao sao testes HTTP concorrentes de ponta a ponta (sem
`django.test.Client`, sem middleware, sem permissao/staff checada). O que
esta sob teste e exatamente o estado compartilhado do ModelAdmin entre
chamadas, que e a causa raiz do defeito original, independente da camada
HTTP por cima.

Defeito original: BlipConfigurationAdmin.get_queryset cacheava o indice
{numero: PhoneLine|None} em `self._blip_line_index` (atributo da instancia
do ModelAdmin). ModelAdmin e registrado uma unica vez por processo
(django.contrib.admin.site._registry), compartilhado entre todas as
threads do mesmo worker. Corrigido com `threading.local()`.

Validacao do modelo de concorrencia real (nao assumida): o Dockerfile/
docker-compose.yml passam `--threads N>1` sem `--worker-class` explicito.
Lido o source de gunicorn 23.0.0 instalado no venv deste projeto
(gunicorn/config.py, `Config.worker_class`/`worker_class_str`): quando
`worker_class` e "sync" (default) e `threads > 1`, gunicorn PROMOVE
automaticamente para `gunicorn.workers.gthread.ThreadWorker` — confirmado
pelo proprio comentario do settings ("If you try to use the sync worker
type and set the threads setting to more than 1, the gthread worker type
will be used instead"). Logo, o deploy real usa threads de SO reais por
worker (gthread), nao workers sync de fato single-threaded — a premissa do
defeito original se confirma, nao e suposicao.

Por que threading.local() isola por REQUISICAO aqui (nao apenas por
thread, o que nao seria suficiente por si so): lido django/contrib/admin/
views/main.py (ChangeList.__init__, linha ~91) — `model_admin.get_queryset
(request)` e chamado exatamente UMA vez por requisicao de changelist,
sincronamente, ANTES de qualquer metodo de list_display ser chamado para
essa mesma requisicao (ChangeList.get_queryset reaproveita
`self.root_queryset`, nao chama `model_admin.get_queryset` de novo). Como
gthread usa threads de SO reais (nao corrotinas/greenlets que poderiam
intercalar DENTRO de uma mesma thread), uma thread processa uma requisicao
por vez, do inicio ao fim, sem interrupcao por outra requisicao no meio —
entao "isolado por thread" equivale a "isolado por requisicao" NESTE
modelo de concorrencia especifico (gthread/WSGI sincrono). Isso deixa de
valer sob um worker assincrono/cooperativo (ex. gevent monkey-patched,
ASGI com greenlets) — o projeto nao usa nenhum dos dois (confirmado:
Dockerfile/docker-compose usam gunicorn+wsgi, sem worker-class gevent/
eventlet, sem Daphne/Uvicorn); se isso mudar, esta suposicao precisa ser
reavaliada.

Limite de ambiente: todos os testes abaixo rodam contra o backend de teste
configurado (SQLite, nesta configuracao de projeto/CI local). Isso prova a
semantica do `threading.local()` em si (primitiva pura do Python, nao
depende do banco) e a ausencia de corrupcao de estado Python entre
threads — nao prova nem exercita comportamento de concorrencia especifico
de PostgreSQL (locks, isolamento de transacao sob carga real). Essa
distincao e deliberada: o defeito e de estado Python compartilhado em
`self`, nao de contencao de banco.
"""

import threading
from datetime import date
from unittest.mock import patch

from django.contrib import admin
from django.db import connection
from django.test import RequestFactory, TransactionTestCase
from django.utils import timezone

from telecom.models import BlipConfiguration, PhoneLine, SIMcard
from users.models import SystemUser

PASSWORD = "StrongPass123"
UNAVAILABLE_LABEL = "Selo indisponível"


class BlipConfigurationAdminConcurrencyTest(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.dev_user = SystemUser.objects.create_user(
            email="svi07-dev@example.com", password=PASSWORD, role=SystemUser.Role.DEV
        )
        self.operator_user = SystemUser.objects.create_user(
            email="svi07-operator@example.com",
            password=PASSWORD,
            role=SystemUser.Role.OPERATOR,
        )
        sim = SIMcard.objects.create(iccid="8900000000000077040", carrier="TIM")
        self.line = PhoneLine.objects.create(
            phone_number="+5511999997740",
            sim_card=sim,
            status=PhoneLine.Status.AVAILABLE,
            origem=PhoneLine.Origem.BLIP,
            whatsapp_seal="META_ONE",
            whatsapp_seal_activation_status="ACTIVE",
            whatsapp_seal_activated_on=date(2026, 8, 1),
            whatsapp_seal_expires_on=date(2026, 9, 25),
        )
        self.config = BlipConfiguration.objects.create(
            blip_id="BLIP-SVI07-CONCURRENCY-1",
            type=BlipConfiguration.ConfigurationType.FLOW,
            description="Fluxo concorrencia",
            phone_number=int(self.line.phone_number),
            key=BlipConfiguration.KeyType.ACCESS,
            value="token-svi07",
        )
        self.admin_instance = admin.site._registry[BlipConfiguration]

    def _request_as(self, user):
        request = RequestFactory().get("/admin/telecom/blipconfiguration/")
        request.user = user
        return request

    def test_second_thread_request_does_not_leak_into_first_threads_render(self):
        """I26 · identidade/autorizacao (Admin), concorrencia real,
        bidirecional · thread A (DEV, autorizado) resolve seu indice;
        thread B (OPERATOR, role excluida de BLIP) resolve o dela
        DEPOIS, com join() completo antes de qualquer leitura — ordem
        garantida, nao dependente de timing. Cada thread deve renderizar
        SOMENTE o que ela mesma resolveu: A continua vendo o selo real
        (nao herda o indice vazio de B) e B continua vendo "Selo
        indisponivel" (nao herda o indice real de A)."""
        with patch.object(timezone, "localdate", return_value=date(2026, 9, 17)):
            request_dev = self._request_as(self.dev_user)
            dev_rows = list(self.admin_instance.get_queryset(request_dev))
            self.assertEqual(len(dev_rows), 1)
            dev_row = dev_rows[0]
            expected_label = self.line.seal_status["label"]

            thread_errors = []
            operator_html_box = {}

            def run_operator_request_in_other_thread():
                try:
                    request_operator = self._request_as(self.operator_user)
                    operator_rows = list(
                        self.admin_instance.get_queryset(request_operator)
                    )
                    operator_html_box["html"] = str(
                        self.admin_instance.phone_number_display(operator_rows[0])
                    )
                except Exception as exc:  # pragma: no cover - propagado abaixo
                    thread_errors.append(exc)
                finally:
                    connection.close()

            other_thread = threading.Thread(target=run_operator_request_in_other_thread)
            other_thread.start()
            other_thread.join(timeout=10)

            self.assertFalse(
                other_thread.is_alive(), "thread secundaria nao terminou a tempo (travou)"
            )
            if thread_errors:
                raise thread_errors[0]

            dev_html = str(self.admin_instance.phone_number_display(dev_row))

        self.assertNotIn(
            UNAVAILABLE_LABEL,
            dev_html,
            "indicador da thread/requisicao DEV foi sobrescrito pelo "
            "indice (vazio) resolvido por outra thread/requisicao "
            "(OPERATOR) — estado compartilhado, nao isolado por "
            "thread/requisicao",
        )
        self.assertIn(expected_label, dev_html)
        self.assertIn("seal-indicator--green", dev_html)

        # Vice-versa: a thread OPERATOR nao pode ter herdado o indice real
        # da thread DEV (que rodou antes, na mesma instancia de admin).
        self.assertIn(
            UNAVAILABLE_LABEL,
            operator_html_box.get("html", ""),
            "requisicao OPERATOR (role sem acesso a BLIP) exibiu um selo "
            "real — deveria mostrar 'Selo indisponivel' pela propria "
            "autorizacao, nao herdar o indice resolvido pela thread DEV",
        )

    def test_successive_requests_on_same_thread_do_not_leak_between_users(self):
        """I26 · requisicoes sucessivas na MESMA thread (sem concorrencia
        real) · como threads de worker sao reaproveitadas entre
        requisicoes (gthread), confirma que uma requisicao OPERATOR
        seguida de uma requisicao DEV, na mesma thread/instancia, nao
        deixa resíduo: cada get_queryset novo substitui o indice por
        completo antes da proxima renderizacao."""
        with patch.object(timezone, "localdate", return_value=date(2026, 9, 17)):
            request_operator = self._request_as(self.operator_user)
            operator_rows = list(self.admin_instance.get_queryset(request_operator))
            operator_html = str(
                self.admin_instance.phone_number_display(operator_rows[0])
            )
            self.assertIn(UNAVAILABLE_LABEL, operator_html)

            request_dev = self._request_as(self.dev_user)
            dev_rows = list(self.admin_instance.get_queryset(request_dev))
            dev_html = str(self.admin_instance.phone_number_display(dev_rows[0]))
            expected_label = self.line.seal_status["label"]

        self.assertNotIn(UNAVAILABLE_LABEL, dev_html)
        self.assertIn(expected_label, dev_html)
        self.assertIn("seal-indicator--green", dev_html)

    def test_failed_get_queryset_does_not_leave_a_render_reachable_via_normal_flow(self):
        """I26 · caminho de excecao · se build_authorized_blip_line_index
        falhar DURANTE get_queryset (ex.: erro de banco), a escrita do
        indice nunca acontece (nenhuma linha alcancada apos a excecao) —
        confirmado que get_queryset propaga a excecao (nao a engole) e que
        uma chamada POSTERIOR, bem-sucedida, de outro usuario, produz o
        indice correto, sem residuo da tentativa que falhou. Isso espelha
        o fluxo real do Django: ChangeList.__init__ chama model_admin.
        get_queryset(request) e, se ela levantar, a requisicao falha antes
        de qualquer render de list_display — entao list_display nunca le
        um indice de uma chamada que nao terminou."""
        with patch.object(timezone, "localdate", return_value=date(2026, 9, 17)):
            request_dev = self._request_as(self.dev_user)

            with patch(
                "telecom.admin.build_authorized_blip_line_index",
                side_effect=RuntimeError("falha simulada de banco"),
            ):
                with self.assertRaises(RuntimeError):
                    self.admin_instance.get_queryset(request_dev)

            # Chamada seguinte, bem-sucedida, de outro usuario na mesma
            # thread/instancia: deve produzir o indice correto DELA
            # mesma, sem herdar nada da tentativa anterior que falhou.
            request_operator = self._request_as(self.operator_user)
            operator_rows = list(self.admin_instance.get_queryset(request_operator))
            operator_html = str(
                self.admin_instance.phone_number_display(operator_rows[0])
            )

        self.assertIn(UNAVAILABLE_LABEL, operator_html)
