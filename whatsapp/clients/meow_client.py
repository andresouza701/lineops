import json
from urllib import error, parse, request

from django.conf import settings

from whatsapp.clients.exceptions import (
    MeowClientBadRequestError,
    MeowClientConflictError,
    MeowClientNotFoundError,
    MeowClientResponseError,
    MeowClientTimeoutError,
    MeowClientUnauthorizedError,
    MeowClientUnavailableError,
)

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


class MeowClient:
    def __init__(self, base_url: str, *, timeout: int | None = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout or settings.WHATSAPP_MEOW_TIMEOUT_SECONDS

    def health_check(self):
        return self._request("GET", "/api/health")

    def create_session(self, session_id: str):
        return self._request(
            "POST",
            "/api/sessions",
            payload={"session_id": session_id},
        )

    def get_session(self, session_id: str):
        encoded_session_id = parse.quote(session_id, safe="")
        return self._request("GET", f"/api/sessions/{encoded_session_id}")

    def connect_session(self, session_id: str):
        encoded_session_id = parse.quote(session_id, safe="")
        return self._request(
            "POST",
            f"/api/sessions/{encoded_session_id}/connect",
            payload={},
        )

    def disconnect_session(self, session_id: str):
        encoded_session_id = parse.quote(session_id, safe="")
        return self._request(
            "POST",
            f"/api/sessions/{encoded_session_id}/disconnect",
            payload={},
        )

    def delete_session(self, session_id: str):
        encoded_session_id = parse.quote(session_id, safe="")
        return self._request("DELETE", f"/api/sessions/{encoded_session_id}/delete")

    def get_qr(self, session_id: str):
        response = self.get_session(session_id)
        details = response.get("details") or {}
        qr_code = self._normalize_qr_code(details.get("qrCode"))
        return {
            "has_qr": details.get("hasQR", False),
            "qr_code": qr_code,
            "qr_expires": details.get("qrExpires"),
            "connected": details.get("connected", False),
            "raw": response,
        }

    def _normalize_qr_code(self, qr_code):
        if not isinstance(qr_code, str):
            return qr_code

        if qr_code.startswith("data:") and "," in qr_code:
            _, encoded_data = qr_code.split(",", 1)
            return encoded_data

        return qr_code

    def _request(self, method: str, path: str, *, payload: dict | None = None):
        headers = {
            "Accept": "application/json",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        http_request = request.Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw_body = response.read()
        except error.HTTPError as exc:
            detail = self._extract_error_detail(exc)
            raise self._map_http_error(exc.code, detail) from exc
        except error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise MeowClientTimeoutError(
                    "Tempo esgotado ao chamar o Meow."
                ) from exc
            raise MeowClientUnavailableError(
                f"Nao foi possivel conectar ao Meow: {exc.reason}"
            ) from exc
        except TimeoutError as exc:
            raise MeowClientTimeoutError("Tempo esgotado ao chamar o Meow.") from exc

        if not raw_body:
            return {}

        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise MeowClientResponseError(
                "O Meow retornou um payload invalido.",
                detail=raw_body.decode("utf-8", errors="ignore"),
            ) from exc

    def _extract_error_detail(self, exc: error.HTTPError):
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""

        if not body:
            return exc.reason

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body

        return (
            payload.get("detail")
            or payload.get("message")
            or payload.get("error")
            or body
        )

    def _map_http_error(self, status_code: int, detail):
        message = f"Erro do Meow ({status_code})."
        if status_code == HTTP_BAD_REQUEST:
            return MeowClientBadRequestError(
                message,
                status_code=status_code,
                detail=detail,
            )
        if status_code in {401, 403}:
            return MeowClientUnauthorizedError(
                message,
                status_code=status_code,
                detail=detail,
            )
        if status_code == HTTP_NOT_FOUND:
            return MeowClientNotFoundError(
                message,
                status_code=status_code,
                detail=detail,
            )
        if status_code == HTTP_CONFLICT:
            return MeowClientConflictError(
                message,
                status_code=status_code,
                detail=detail,
            )
        return MeowClientResponseError(
            message,
            status_code=status_code,
            detail=detail,
        )
