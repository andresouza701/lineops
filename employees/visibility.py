"""Politica centralizada de visibilidade de funcionarios inativos (FVI-04).

Fonte de verdade: docs/superpowers/specs/2026-10-14-inactive-system-user-visibility-design.md

Regra unica, reutilizavel por Admin/views/services: ADMIN e DEV preservam
visibilidade de ``Employee`` com ``status == Employee.Status.INACTIVE``
(excecao de role, nao de permissao tecnica: ``is_staff``/``is_superuser``
nao substituem esta excecao). Os demais quatro papeis (SUPER, BACKOFFICE,
GERENTE, OPERATOR) nao veem funcionarios inativos em diretorios,
seletores, Acoes do Dia ou novas associacoes.

Este modulo nao reimplementa escopo organizacional
(``scope_employee_queryset``/``get_supervised_employees_queryset``) nem
exclusao logica (``Employee.is_deleted``, ja filtrada pelo manager
padrao): compoe-se SOBRE o resultado dessas consultas, na mesma ordem
que o codigo ja usa hoje (escopo -> visibilidade de atividade).

A excecao aprovada de pendencias (funcionario inativo com pendencia ou
alocacao elegivel preserva acesso) e logica ESPECIFICA do dominio de
pendencias/alocacoes e vive em ``pendencies/views.py``, nao aqui, para
evitar import circular entre apps.
"""

from users.models import SystemUser
from users.visibility import KEEP_CURRENT_LABEL, KEEP_CURRENT_TOKEN, viewer_is_exempt

from .models import Employee

VISIBILITY_EXEMPT_ROLES = (SystemUser.Role.ADMIN, SystemUser.Role.DEV)

# FVI-06 (fechamento do achado 1 da conferencia corretiva de FVI-05):
# rotulo neutro para a representacao OPERACIONAL de um Employee oculto,
# usado em titulo/subtitulo/breadcrumb/changelist/mensagem de sucesso de
# LineAllocationAdmin/AllocationPendencyAdmin -- nunca em Employee.__str__
# nem em qualquer __str__ de modelo (historico, autoria e relatorios
# preservados, conforme decisao explicita do usuario).
INACTIVE_EMPLOYEE_LABEL = "Funcionário inativo"


def visible_employees_queryset(viewer, queryset=None):
    """Retorna o queryset de Employee visivel para o viewer: integral
    para ADMIN/DEV, restrito a status=ACTIVE para os demais papeis (ou
    ausencia de viewer)."""
    base = queryset if queryset is not None else Employee.objects.all()
    if viewer_is_exempt(viewer):
        return base
    return base.filter(status=Employee.Status.ACTIVE)


def employee_is_visible(viewer, employee):
    if employee is None:
        return False
    if viewer_is_exempt(viewer):
        return True
    return employee.status == Employee.Status.ACTIVE


def resolve_employee_fk_keep_current(viewer, persisted_employee_id):
    """Para campos FK operacionais de ``employee`` em Admin (F16/F17):
    retorna (queryset_visivel, masked_id). ``masked_id`` e o
    ``persisted_employee_id`` quando esse vinculo esta oculto para o
    viewer (precisa do marcador neutro ``__keep_current__``); ``None``
    quando nao ha vinculo oculto a preservar (criacao, campo vazio,
    vinculo ja visivel ou viewer isento)."""
    visible = visible_employees_queryset(viewer, Employee.objects.all())
    masked_id = None
    if persisted_employee_id is not None and not visible.filter(
        pk=persisted_employee_id
    ).exists():
        masked_id = persisted_employee_id
    return visible, masked_id


def apply_keep_current_to_employee_formfield(formfield, masked_employee_id):
    """Mesmo mecanismo ja aprovado para technical_responsible
    (AllocationPendencyAdmin): adiciona uma opcao SINTETICA
    (KEEP_CURRENT_TOKEN/KEEP_CURRENT_LABEL) e resolve ``to_python`` para
    o Employee realmente persistido NESTE registro (relido do banco a
    cada requisicao, nunca de pk enviado pelo cliente) -- sem reincluir
    o PK/identidade oculta no queryset/choices."""
    if masked_employee_id is None or formfield is None:
        return formfield

    formfield.choices = [(KEEP_CURRENT_TOKEN, KEEP_CURRENT_LABEL)] + list(
        formfield.choices
    )
    original_to_python = formfield.to_python

    def to_python(value, _orig=original_to_python, _pk=masked_employee_id):
        if value == KEEP_CURRENT_TOKEN:
            return Employee.objects.filter(pk=_pk).first()
        return _orig(value)

    formfield.to_python = to_python
    return formfield


def masked_employee_label(viewer, employee):
    """FVI-06: representacao OPERACIONAL contextual de ``employee`` para
    apresentacao (changelist, titulo, subtitulo, breadcrumb e mensagem
    de sucesso dos Admins de coexistencia Alocacoes/Pendencias) --
    identidade real (``str(employee)``) quando o vinculo esta visivel
    para o viewer (ativo, ou viewer isento ADMIN/DEV via
    ``employee_is_visible``), ``INACTIVE_EMPLOYEE_LABEL`` quando oculto.
    Nunca usado para o <select> do campo employee (que usa o marcador
    __keep_current__, mecanismo separado) nem para __str__ de modelo."""
    if employee is None:
        return None
    if employee_is_visible(viewer, employee):
        return str(employee)
    return INACTIVE_EMPLOYEE_LABEL


class EmployeeLinkedDisplayProxy:
    """FVI-06: envoltorio TRANSPARENTE de uma unica instancia persistida
    (LineAllocation/AllocationPendency), usado somente para compor a
    mensagem de sucesso pos-save do Admin (``response_change``) sem
    reintroduzir a identidade oculta pelo <select> do campo employee.
    Delega todo atributo/metodo ao objeto real via ``__getattr__`` (pk,
    _meta, serializable_value etc. continuam funcionando normalmente
    para o restante da resposta) -- apenas ``__str__`` retorna o texto
    ja mascarado. Instancia nova por chamada, nunca atribuida a self nem
    a ModelAdmin: sem estado compartilhado entre requisicoes."""

    __slots__ = ("_wrapped", "_masked_text")

    def __init__(self, wrapped, masked_text):
        self._wrapped = wrapped
        self._masked_text = masked_text

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def __str__(self):
        return self._masked_text


def wrap_admin_form_with_employee_keep_current(
    form_class, masked_employee_id, *, field_name="employee"
):
    """Sobrescreve ``initial[field_name]`` para o token quando houver
    vinculo oculto a preservar -- sem isso, model_to_dict preencheria o
    initial com o PK real, que nao esta mais entre as choices."""
    if masked_employee_id is None:
        return form_class

    class FormWithEmployeeKeepCurrent(form_class):
        def __init__(form_self, *args, **init_kwargs):
            super().__init__(*args, **init_kwargs)
            form_self.initial[field_name] = KEEP_CURRENT_TOKEN

    return FormWithEmployeeKeepCurrent
