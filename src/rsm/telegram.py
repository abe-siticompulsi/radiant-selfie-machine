"""Il client del bot Telegram del servizio. Nessuna politica: chiama l'API e
restituisce quello che serve.

Il token sta nell'URL di ogni chiamata. Per questo gli errori non riportano mai
il testo delle eccezioni di httpx, che può contenere l'URL, e non le
incatenano (`from None`): un `log.exception` le stamperebbe. Per lo stesso
motivo `principale.py` alza il livello del logger `httpx`, che al livello INFO
scriverebbe ogni URL, token compreso.

Nessuna chiamata usa `parse_mode`: i testi, motivi compresi, sono semplici.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

Pulsanti = list[list[tuple[str, str]]]


class TelegramError(RuntimeError):
    """Una chiamata all'API di Telegram non è andata a buon fine."""


def _tastiera(pulsanti: Pulsanti) -> dict:
    return {
        "inline_keyboard": [
            [{"text": testo, "callback_data": dati} for testo, dati in riga] for riga in pulsanti
        ]
    }


class BotTelegram:
    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self._base = f"https://api.telegram.org/bot{token}/"
        self._http = http or httpx.Client(timeout=httpx.Timeout(10.0))

    def _chiama(
        self,
        metodo: str,
        *,
        corpo: dict | None = None,
        campi: dict | None = None,
        file: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        argomenti: dict[str, Any] = {}
        if corpo is not None:
            argomenti["json"] = corpo
        if campi is not None:
            argomenti["data"] = campi
        if file is not None:
            argomenti["files"] = file
        if timeout is not None:
            argomenti["timeout"] = timeout
        try:
            risposta = self._http.post(self._base + metodo, **argomenti)
        except httpx.HTTPError as e:
            raise TelegramError(f"{metodo}: errore di rete ({type(e).__name__})") from None
        try:
            contenuto = risposta.json()
        except ValueError:
            raise TelegramError(
                f"{metodo}: risposta non JSON (HTTP {risposta.status_code})"
            ) from None
        if not contenuto.get("ok"):
            descrizione = contenuto.get("description", "errore senza descrizione")
            raise TelegramError(f"{metodo}: {descrizione}")
        return contenuto["result"]

    def scrivi(self, chat_id: int, testo: str) -> int:
        risultato = self._chiama("sendMessage", corpo={"chat_id": chat_id, "text": testo})
        return risultato["message_id"]

    def manda_foto(self, chat_id: int, dati: bytes, didascalia: str, pulsanti: Pulsanti) -> int:
        risultato = self._chiama(
            "sendPhoto",
            campi={
                "chat_id": str(chat_id),
                "caption": didascalia,
                "reply_markup": json.dumps(_tastiera(pulsanti)),
            },
            file={"photo": ("selfie.jpg", dati, "image/jpeg")},
            timeout=30.0,
        )
        return risultato["message_id"]

    def modifica_didascalia(
        self, chat_id: int, messaggio: int, testo: str, pulsanti: Pulsanti | None = None
    ) -> None:
        self._chiama(
            "editMessageCaption",
            corpo={
                "chat_id": chat_id,
                "message_id": messaggio,
                "caption": testo,
                "reply_markup": _tastiera(pulsanti or []),
            },
        )

    def chiedi_risposta(self, chat_id: int, testo: str) -> int:
        risultato = self._chiama(
            "sendMessage",
            corpo={
                "chat_id": chat_id,
                "text": testo,
                "reply_markup": {"force_reply": True, "input_field_placeholder": "Il motivo"},
            },
        )
        return risultato["message_id"]

    def rispondi_tocco(self, tocco_id: str, testo: str) -> None:
        self._chiama(
            "answerCallbackQuery", corpo={"callback_query_id": tocco_id, "text": testo[:200]}
        )

    def aggiornamenti(self, offset: int | None, attesa: int) -> list[dict]:
        corpo: dict[str, Any] = {"timeout": attesa, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            corpo["offset"] = offset
        return self._chiama("getUpdates", corpo=corpo, timeout=attesa + 10.0)

    def webhook_attivo(self) -> bool:
        return bool(self._chiama("getWebhookInfo").get("url"))
