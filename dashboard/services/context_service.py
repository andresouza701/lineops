from dashboard.services.query_service import get_pending_action_counts_for_user


def get_pending_actions_count_for_user(user):
    action_counts = get_pending_action_counts_for_user(user)
    return int(action_counts.get("new_number", 0) or 0) + int(
        action_counts.get("reconnect_whatsapp", 0) or 0
    )

