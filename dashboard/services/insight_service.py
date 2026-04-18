from telecom.models import PhoneLine

PERCENT_CRITICAL_THRESHOLD = 20
PERCENT_WARNING_THRESHOLD = 10
COUNT_CRITICAL_THRESHOLD = 10
COUNT_WARNING_THRESHOLD = 5


def _level_for_percentage(value):
    if value >= PERCENT_CRITICAL_THRESHOLD:
        return "critical"
    if value >= PERCENT_WARNING_THRESHOLD:
        return "warning"
    return "ok"


def _level_for_count(value):
    if value >= COUNT_CRITICAL_THRESHOLD:
        return "critical"
    if value >= COUNT_WARNING_THRESHOLD:
        return "warning"
    return "ok"


def build_dashboard_exception_cards(
    *,
    daily_indicators,
    line_status_counts,
    pending_action_counts,
    action_board_url,
):
    daily = daily_indicators or []
    latest = daily[-1] if daily else {}

    latest_sem_whats = float(latest.get("perc_sem_whats", 0) or 0)
    latest_descoberto = int(latest.get("total_descoberto_dia", 0) or 0)
    latest_reconectados = int(latest.get("reconectados", 0) or 0)

    line_status_map = {
        entry["value"]: int(entry.get("count", 0)) for entry in line_status_counts or []
    }
    blocked_lines = line_status_map.get(PhoneLine.Status.SUSPENDED, 0) + line_status_map.get(
        PhoneLine.Status.CANCELLED, 0
    )

    pending_new_number_count = int(pending_action_counts.get("new_number", 0) or 0)
    pending_reconnect_whatsapp_count = int(
        pending_action_counts.get("reconnect_whatsapp", 0) or 0
    )

    return {
        "exception_cards": [
            {
                "title": "Cobertura Whats",
                "value": f"{latest_sem_whats:.1f}%",
                "description": "Percentual da equipe sem linha ativa.",
                "level": _level_for_percentage(latest_sem_whats),
                "action_label": "Ver usuarios",
                "action_url": "/employees/",
            },
            {
                "title": "Linhas bloqueadas",
                "value": blocked_lines,
                "description": "Linhas suspensas ou canceladas no inventario.",
                "level": _level_for_count(blocked_lines),
                "action_label": "Ver telecom",
                "action_url": "/telecom/",
            },
            {
                "title": "Pendencia - Numero Novo",
                "value": pending_new_number_count,
                "description": "Pendencias marcadas como precisa numero novo.",
                "level": _level_for_count(pending_new_number_count),
                "action_label": "Ver pendencias",
                "action_url": action_board_url,
            },
            {
                "title": "Pendencia - Reconexao Whats",
                "value": pending_reconnect_whatsapp_count,
                "description": "Pendencias marcadas como precisa reconectar WhatsApp.",
                "level": _level_for_count(pending_reconnect_whatsapp_count),
                "action_label": "Ver pendencias",
                "action_url": action_board_url,
            },
            {
                "title": "Descobertos hoje",
                "value": latest_descoberto,
                "description": "Usuarios sem linha no fechamento do dia.",
                "level": _level_for_count(latest_descoberto),
                "action_label": "Ir para cadastro",
                "action_url": "/allocations/",
            },
            {
                "title": "Reconectados hoje",
                "value": latest_reconectados,
                "description": "Recuperacoes efetivas no dia atual.",
                "level": "ok" if latest_reconectados > 0 else "warning",
                "action_label": "Detalhar telecom",
                "action_url": "/telecom/",
            },
        ]
    }

