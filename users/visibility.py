"""Politica centralizada de visibilidade de contas de acesso inativas (UVI-04).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md

Regra unica, reutilizavel por Admin/forms/views: ADMIN e DEV preservam
visibilidade de ``SystemUser`` com ``is_active=False`` (excecao de role, nao
de permissao tecnica: ``is_staff``/``is_superuser`` nao substituem esta
excecao). Os demais quatro papeis (SUPER, BACKOFFICE, GERENTE, OPERATOR) nao
veem contas inativas em diretorios, seletores ou novas associacoes.

O "viewer" deve vir sempre da request (``request.user``), nunca de dado
enviado pelo cliente. Ausencia de viewer (``None``) e tratada como o caso
mais restrito -- nenhuma excecao implicita de ADMIN.

Este modulo nao filtra o manager global de ``SystemUser`` (``objects``),
nem altera autenticacao ou helpers de escopo de funcionarios/linhas
(``get_managed_supervisor_emails``, ``scope_employee_queryset``): essas
consultas permanecem fora do dominio de visibilidade por decisao explicita
do contrato (U11).
"""

from django.db.models import Q

from .models import SystemUser

KEEP_CURRENT_TOKEN = "__keep_current__"
# UVI-06 (correcao): os tres literais abaixo sao parte do contrato
# (UVI-01/02) desde a origem -- a grafia com acento sempre foi a
# aprovada; a ausencia de teste cobrando a grafia exata NAO tornava a
# grafia sem acento aceitavel, apenas nao havia prova automatizada do
# desvio. Retificacao explicita: a entrega anterior (UVI-06, achado
# cosmetico) tratou isso como "fora do contrato por ausencia de teste" --
# essa leitura estava errada e e retirada aqui.
KEEP_CURRENT_LABEL = "Manter vínculo atual"
NO_ACTIVE_ACCOUNTS_LABEL = "Nenhum usuário ativo disponível"
INACTIVE_ACCOUNT_LABEL = "Usuário inativo"

VISIBILITY_EXEMPT_ROLES = (SystemUser.Role.ADMIN, SystemUser.Role.DEV)


def viewer_role(viewer):
    role = getattr(viewer, "role", None)
    return role or None


def viewer_is_exempt(viewer):
    """ADMIN/DEV sao excecao de ROLE, nao de permissao tecnica. Viewer
    ausente (None) nunca e excecao implicita."""
    if viewer is None:
        return False
    if not getattr(viewer, "is_authenticated", True):
        return False
    return viewer_role(viewer) in VISIBILITY_EXEMPT_ROLES


def visible_accounts_queryset(viewer, queryset=None):
    """Retorna o queryset de SystemUser visivel para o viewer: integral
    para ADMIN/DEV, restrito a is_active=True para os demais papeis (ou
    ausencia de viewer)."""
    base = queryset if queryset is not None else SystemUser.objects.all()
    if viewer_is_exempt(viewer):
        return base
    return base.filter(is_active=True)


def is_account_visible(viewer, system_user):
    if system_user is None:
        return False
    if viewer_is_exempt(viewer):
        return True
    return bool(system_user.is_active)


def account_is_hidden_for_viewer(viewer, email, *, role=None):
    """True quando existe uma conta com este e-mail, ela esta inativa, e o
    viewer nao tem a excecao de role -- ou seja, o e-mail persistido
    corresponde a uma conta oculta para este viewer especificamente."""
    email = (email or "").strip()
    if not email:
        return False
    if viewer_is_exempt(viewer):
        return False
    lookup = SystemUser.objects.filter(email__iexact=email)
    if role is not None:
        lookup = lookup.filter(role=role)
    return lookup.filter(is_active=False).exists()


def resolve_inactive_email_labels(viewer, emails):
    """UVI-05 (retificado na conferencia corretiva): resolve em UMA unica
    consulta quais dos ``emails`` informados correspondem a uma conta
    ``SystemUser`` inativa, para a camada de apresentacao
    (employee_list/employee_detail/manager_dashboard) neutralizar a
    identidade sem crescer linearmente por item (T12) e sem guardar
    estado entre requisicoes/viewers.

    Depende do viewer, reutilizando ``viewer_is_exempt`` (a MESMA excecao
    de role ja usada por ``visible_accounts_queryset``/
    ``account_is_hidden_for_viewer`` desde UVI-04): para ADMIN/DEV retorna
    sempre um set vazio (nenhuma consulta de mascaramento e feita -- a
    excecao e de autorizacao previa, nao uma concessao nova de rota), e
    para os quatro papeis restritos (ou ausencia de viewer) resolve
    normalmente. A entrega original desta etapa ignorava o viewer e
    mascarava para qualquer papel, inclusive ADMIN/DEV -- desvio relatado
    e corrigido aqui; a politica de role continua centralizada neste
    modulo, nunca duplicada em views/templates.

    Retorna um set de e-mails normalizados (strip + casefold) ocultos
    PARA ESTE VIEWER. Valores sem conta correspondente (strings legadas)
    nunca entram no set, preservando o tratamento legado existente."""
    if viewer_is_exempt(viewer):
        return set()
    normalized = {
        email.strip() for email in emails if email and email.strip()
    }
    if not normalized:
        return set()
    lookup = Q()
    for email in normalized:
        lookup |= Q(email__iexact=email)
    inactive_emails = SystemUser.objects.filter(lookup, is_active=False).values_list(
        "email", flat=True
    )
    return {email.casefold() for email in inactive_emails}


def mask_inactive_email(email, inactive_casefold_set, *, label=INACTIVE_ACCOUNT_LABEL):
    """Aplica ``label`` quando ``email`` (apos strip+casefold) estiver no
    set resolvido em lote por ``resolve_inactive_email_labels``; preserva o
    valor original para valores vazios ou sem conta correspondente."""
    if not email:
        return email
    if email.strip().casefold() in inactive_casefold_set:
        return label
    return email


def resolve_all_inactive_emails_casefold(viewer):
    """UVI-06 (correcao): projecao em lote para colunas de ``list_display``
    do Admin (changelist inteira), uma unica consulta por REQUISICAO,
    independente do numero de linhas da pagina -- nunca por linha (sem
    N+1) e nunca cacheada entre requisicoes (``ModelAdmin`` e
    compartilhado entre requests; o resultado deve ser calculado a cada
    chamada de ``get_list_display`` e capturado por closure, nunca
    atribuido a ``self``). ADMIN/DEV retornam set vazio (excecao de role,
    sem consulta alguma)."""
    if viewer_is_exempt(viewer):
        return set()
    return {
        email.casefold()
        for email in SystemUser.objects.filter(is_active=False).values_list(
            "email", flat=True
        )
    }


class KeepCurrentInvalidContext(Exception):
    """Marcador __keep_current__ usado fora de contexto valido: criacao,
    campo sem vinculo persistido, ou vinculo persistido que nao esta
    oculto para o viewer. Callers devem traduzir para ValidationError de
    campo generica, sem citar o valor."""


def account_text_field_initial(viewer, persisted_email):
    """UVI-06 (correcao): valor inicial a exibir em GET para um campo de
    texto livre de conta operacional (SystemUserAdmin.supervisor_email/
    manager_email, EmployeeAdminForm.corporate_email/manager_email): o
    token neutro quando o valor persistido existe e esta oculto para o
    viewer (nunca a identidade real no HTML/initial do form), o valor
    real nos demais casos (vazio, ja visivel, ou excecao ADMIN/DEV)."""
    if not persisted_email:
        return persisted_email
    if account_is_hidden_for_viewer(viewer, persisted_email):
        return KEEP_CURRENT_TOKEN
    return persisted_email


def redisplay_value_for_rejected_submission(viewer, submitted_value, persisted_email):
    """UVI-06d (correcao): resolve a REPRESENTACAO (redisplay apos POST
    invalido via ``Field.bound_data``) de um valor submetido que resolve
    para conta oculta -- nunca usado para validacao, que continua lendo
    o valor bruto original (``_clean_fields``) e recusando normalmente.

    Retorna ``None`` quando a representacao padrao (o proprio valor
    submetido) deve ser usada -- token vazio, valor que nao resolve
    para conta oculta (legado/ativo, preserva a escolha do viewer).

    Quando o valor submetido resolve para conta oculta, SO retorna o
    token ``__keep_current__`` se existir, NESTE campo, um vinculo
    persistido que tambem esteja oculto para o viewer -- ou seja, um
    vinculo preservavel de fato. Achado real (UVI-06d): a versao
    anterior retornava o token sempre que o valor submetido era oculto,
    mesmo sem vinculo persistido algum (``manager_email=None``) ou com
    vinculo persistido ATIVO -- nesses dois casos o campo nunca foi
    trocado para CharField (continua ``type="email"``), entao o token
    virava um "e-mail" invalido no proprio input, e nao havia vinculo
    nenhum que ele pudesse legitimamente representar. Nesses casos a
    representacao correta e vazia (``""``), nunca o token nem o valor
    oculto -- com o erro explicito de campo permanecendo, sem gravar
    essa representacao em lugar algum (e so para renderizacao)."""
    value = (submitted_value or "").strip()
    if not value or value == KEEP_CURRENT_TOKEN:
        return None
    if not account_is_hidden_for_viewer(viewer, value):
        return None
    if persisted_email and account_is_hidden_for_viewer(viewer, persisted_email):
        return KEEP_CURRENT_TOKEN
    return ""


def resolve_account_text_field_post(viewer, raw_value, persisted_email):
    """UVI-06 (correcao): resolve o valor POSTado de um campo de texto
    livre de conta operacional. O token so e valido quando ha vinculo
    persistido oculto para ESTE viewer (edicao real de um vinculo ja
    existente e oculto) -- resolvido a partir do valor persistido no
    banco, nunca de ``self.instance`` ja mutado pelo ModelForm nem de
    dado enviado pelo cliente alem do proprio token. Em qualquer outro
    contexto (criacao, campo sem vinculo, vinculo ja visivel) levanta
    ``KeepCurrentInvalidContext``. Fora do token, retorna o valor bruto
    sem alteracao -- a validacao de conta oculta continua a cargo do
    chamador (``account_is_hidden_for_viewer``), que nao muda aqui."""
    if raw_value == KEEP_CURRENT_TOKEN:
        if persisted_email and account_is_hidden_for_viewer(viewer, persisted_email):
            return persisted_email
        raise KeepCurrentInvalidContext()
    return raw_value
