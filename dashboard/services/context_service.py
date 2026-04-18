from dashboard.services.query_service import get_pending_action_counts_for_user


def get_pending_action_counts_cached(request):
    """
    Retorna o dict de contagens de pendencias cacheado no request.

    Evita que o context processor e o view executem a mesma query duas vezes
    na mesma requisicao. O cache vive no objeto request e expira naturalmente
    ao final do ciclo HTTP.
    """
    if not hasattr(request, "_pending_action_counts"):
        request._pending_action_counts = get_pending_action_counts_for_user(
            request.user
        )
    return request._pending_action_counts
