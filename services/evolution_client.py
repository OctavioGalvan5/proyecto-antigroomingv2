"""Cliente para Evolution API — modo multi-instancia.

Cada `ChildInstance` de nuestra app corresponde a una `instance` en Evolution.
Este módulo encapsula todas las llamadas HTTP. Ningún otro archivo debería
armar URLs de Evolution a mano.

Endpoints Evolution que usamos:
    POST   /instance/create
    GET    /instance/connect/{instance}
    GET    /instance/connectionState/{instance}
    POST   /instance/logout/{instance}
    DELETE /instance/delete/{instance}
    POST   /webhook/set/{instance}   (por si el webhook no se setea en /create)

Referencia: https://doc.evolution-api.com/
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from config import Config

logger = logging.getLogger(__name__)


class EvolutionAPIError(RuntimeError):
    """Error genérico en la comunicación con Evolution API."""

    def __init__(self, message: str, status_code: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass
class InstanceCreationResult:
    """Resultado de crear una instancia.

    `qr_base64` puede venir directamente en la respuesta de `/instance/create`
    (Evolution lo devuelve como data URL). Si no, hay que llamar a `connect`.
    """
    instance_name: str
    qr_base64: str | None
    raw: dict


class EvolutionClient:
    """Cliente HTTP para Evolution API.

    Uso típico::

        client = EvolutionClient()
        result = client.create_instance("child_a1b2c3", webhook_url="https://.../webhook/evolution")
        # mostrar result.qr_base64 al padre para que el hijo escanee
        state = client.connection_state("child_a1b2c3")  # -> "open" | "connecting" | "close"
    """

    def __init__(self, api_url: str | None = None, api_key: str | None = None, timeout: int = 15):
        self.api_url = (api_url or Config.EVOLUTION_API_URL or "").rstrip("/")
        self.api_key = api_key or Config.EVOLUTION_API_KEY
        self.timeout = timeout

    # ------------------------------------------------------------------ util

    @property
    def is_configured(self) -> bool:
        return bool(self.api_url and self.api_key)

    def _headers(self) -> dict[str, str]:
        return {"apikey": self.api_key, "Content-Type": "application/json"}

    def _request(self, method: str, path: str, *, json: dict | None = None) -> dict:
        if not self.is_configured:
            raise EvolutionAPIError("Evolution API no está configurada (falta URL o KEY)")

        url = f"{self.api_url}{path}"
        try:
            resp = requests.request(method, url, headers=self._headers(),
                                    json=json, timeout=self.timeout)
        except requests.RequestException as exc:
            logger.exception("Fallo de red hablando con Evolution API: %s %s", method, url)
            raise EvolutionAPIError(f"Fallo de red: {exc}") from exc

        if not resp.ok:
            logger.error("Evolution API respondió %s en %s %s: %s",
                         resp.status_code, method, url, resp.text[:500])
            raise EvolutionAPIError(
                f"Evolution API {resp.status_code} en {method} {path}",
                status_code=resp.status_code, payload=resp.text,
            )

        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    # ---------------------------------------------------------- operaciones

    def create_instance(self, instance_name: str, *, webhook_url: str) -> InstanceCreationResult:
        """Crea una instancia y le asocia el webhook.

        La API de Evolution acepta el webhook en `/instance/create` mismo.
        Se pide `qrcode=True` para que devuelva el QR de una.
        """
        payload = {
            "instanceName": instance_name,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": webhook_url,
                "byEvents": False,
                "base64": False,
                "events": [
                    "MESSAGES_UPSERT",
                    "MESSAGES_UPDATE",
                    "CONNECTION_UPDATE",
                    "QRCODE_UPDATED",
                ],
            },
        }
        data = self._request("POST", "/instance/create", json=payload)

        qr_base64 = self._extract_qr(data)
        return InstanceCreationResult(instance_name=instance_name, qr_base64=qr_base64, raw=data)

    def connect(self, instance_name: str) -> dict:
        """Solicita el QR (o reengancha si ya estaba creada)."""
        return self._request("GET", f"/instance/connect/{instance_name}")

    def get_qr(self, instance_name: str) -> str | None:
        """Devuelve el QR base64 más reciente para esta instancia, si aplica."""
        data = self.connect(instance_name)
        return self._extract_qr(data)

    def connection_state(self, instance_name: str) -> str:
        """Devuelve el estado: 'open' (conectado), 'connecting', 'close'."""
        data = self._request("GET", f"/instance/connectionState/{instance_name}")
        state = data.get("instance", {}).get("state") or data.get("state")
        return state or "unknown"

    def logout(self, instance_name: str) -> dict:
        return self._request("POST", f"/instance/logout/{instance_name}")

    def delete_instance(self, instance_name: str) -> dict:
        """Elimina la instancia (usar al revocar consentimiento)."""
        return self._request("DELETE", f"/instance/delete/{instance_name}")

    def set_webhook(self, instance_name: str, webhook_url: str) -> dict:
        """Actualiza el webhook post-hoc si hace falta."""
        payload = {
            "url": webhook_url,
            "byEvents": False,
            "base64": False,
            "events": [
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",
                "CONNECTION_UPDATE",
                "QRCODE_UPDATED",
            ],
        }
        return self._request("POST", f"/webhook/set/{instance_name}", json=payload)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _extract_qr(data: dict) -> str | None:
        """Evolution puede devolver el QR en varias formas segun versión.

        Cubro los shapes conocidos: `qrcode.base64`, `qrcode`, `base64`, o
        adentro de `instance`.
        """
        if not isinstance(data, dict):
            return None
        candidates = [
            data.get("qrcode", {}).get("base64") if isinstance(data.get("qrcode"), dict) else None,
            data.get("qrcode") if isinstance(data.get("qrcode"), str) else None,
            data.get("base64"),
            data.get("instance", {}).get("qrcode", {}).get("base64")
                if isinstance(data.get("instance"), dict) else None,
        ]
        for c in candidates:
            if c:
                return c
        return None
