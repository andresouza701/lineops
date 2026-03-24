class MeowClientError(Exception):
    """Erro base do cliente HTTP do Meow."""


class MeowClientUnavailableError(MeowClientError):
    """O Meow nao respondeu ou nao pode ser alcançado."""


class MeowClientTimeoutError(MeowClientUnavailableError):
    """A chamada ao Meow excedeu o tempo configurado."""


class MeowClientResponseError(MeowClientError):
    """O Meow respondeu com erro ou payload invalido."""

    def __init__(self, message, *, status_code=None, detail=None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class MeowClientBadRequestError(MeowClientResponseError):
    pass


class MeowClientUnauthorizedError(MeowClientResponseError):
    pass


class MeowClientNotFoundError(MeowClientResponseError):
    pass


class MeowClientConflictError(MeowClientResponseError):
    pass
