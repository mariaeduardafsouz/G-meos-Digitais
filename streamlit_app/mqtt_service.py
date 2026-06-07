from __future__ import annotations

import json
import threading
import time
import uuid
from collections import deque
from typing import Any

import paho.mqtt.client as mqtt


class MqttTelemetryService:
    """Background MQTT client used by the Streamlit dashboard."""

    def __init__(
        self,
        broker: str = "broker.hivemq.com",
        port: int = 1883,
        topic_prefix: str = "ph",
        max_samples: int = 1000,
    ) -> None:
        self.broker = broker
        self.port = int(port)
        self.topic_prefix = topic_prefix.strip().strip("/") or "ph"
        self.max_samples = int(max_samples)

        self._lock = threading.Lock()
        self._rows: deque[dict[str, Any]] = deque(maxlen=self.max_samples)
        self._events: deque[dict[str, Any]] = deque(maxlen=100)
        self._last_values: dict[str, Any] = {}
        self._started = False
        self._connected = False
        self._last_error: str | None = None
        self._last_seen: float | None = None

        self.client = self._build_client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    @property
    def stats_topic(self) -> str:
        return f"{self.topic_prefix}/estatisticas"

    @property
    def command_calibrate_topic(self) -> str:
        return f"{self.topic_prefix}/cmd/calibrar"

    @property
    def command_buffer_topic(self) -> str:
        return f"{self.topic_prefix}/cmd/buffer"

    @property
    def command_interval_topic(self) -> str:
        return f"{self.topic_prefix}/cmd/intervalo"

    def _build_client(self) -> mqtt.Client:
        client_id = f"streamlit_ph_dashboard_{uuid.uuid4().hex[:8]}"
        try:
            return mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                protocol=mqtt.MQTTv311,
            )
        except Exception:
            return mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

    def start(self) -> None:
        if self._started:
            return

        self._started = True
        try:
            self.client.connect_async(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as exc:
            self._set_error(f"Falha ao iniciar MQTT: {exc}")

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as exc:
            self._set_error(f"Falha ao parar MQTT: {exc}")

    def publish_buffer(self, buffer_value: str) -> None:
        self._publish(self.command_buffer_topic, str(buffer_value))

    def publish_calibration(self) -> None:
        self._publish(self.command_calibrate_topic, "reset")

    def publish_interval(self, interval_ms: int) -> None:
        self._publish(self.command_interval_topic, str(int(interval_ms)))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "rows": list(self._rows),
                "events": list(self._events),
                "last_values": dict(self._last_values),
                "connected": self._connected,
                "last_error": self._last_error,
                "last_seen": self._last_seen,
                "broker": self.broker,
                "port": self.port,
                "topic_prefix": self.topic_prefix,
                "stats_topic": self.stats_topic,
            }

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()
            self._events.clear()
            self._last_values.clear()
            self._last_seen = None

    def _publish(self, topic: str, payload: str) -> None:
        try:
            result = self.client.publish(topic, payload)
            if getattr(result, "rc", 0) != mqtt.MQTT_ERR_SUCCESS:
                self._set_error(f"Falha ao publicar em {topic}: rc={result.rc}")
            else:
                self._add_event("comando", topic=topic, payload=payload)
        except Exception as exc:
            self._set_error(f"Falha ao publicar em {topic}: {exc}")

    def _on_connect(self, client: mqtt.Client, _userdata: Any, _flags: Any, reason_code: Any, *_args: Any) -> None:
        success = reason_code == 0 or str(reason_code).lower() in {"0", "success"}
        with self._lock:
            self._connected = bool(success)
            self._last_error = None if success else f"MQTT conectado com codigo inesperado: {reason_code}"

        if success:
            client.subscribe(f"{self.topic_prefix}/#")
            self._add_event("mqtt", topic=f"{self.topic_prefix}/#", payload="subscribed")

    def _on_disconnect(self, _client: mqtt.Client, _userdata: Any, reason_code: Any, *_args: Any) -> None:
        with self._lock:
            self._connected = False
            if reason_code not in (0, None):
                self._last_error = f"MQTT desconectado: {reason_code}"

    def _on_message(self, _client: mqtt.Client, _userdata: Any, message: mqtt.MQTTMessage) -> None:
        topic = message.topic
        payload = message.payload.decode("utf-8", errors="replace")
        now = time.time()

        if topic == self.stats_topic:
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError as exc:
                self._set_error(f"JSON invalido em {topic}: {exc}")
                return

            row = self._normalize_stats(parsed, now)
            with self._lock:
                self._rows.append(row)
                self._last_values.update(row)
                self._last_seen = now
            return

        suffix = topic.removeprefix(f"{self.topic_prefix}/")
        value: Any = payload
        try:
            value = float(payload)
        except ValueError:
            pass

        with self._lock:
            self._last_values[suffix] = value
            self._last_seen = now
        self._add_event("mqtt", topic=topic, payload=payload)

    def _normalize_stats(self, data: dict[str, Any], received_at: float) -> dict[str, Any]:
        row = {
            "received_at": received_at,
            "received_time": time.strftime("%H:%M:%S", time.localtime(received_at)),
            "leitura": self._as_float(data.get("leitura")),
            "referencia": self._as_float(data.get("referencia")),
            "erro": self._as_float(data.get("erro")),
            "erroPct": self._as_float(data.get("erroPct")),
            "totalAmostras": int(self._as_float(data.get("totalAmostras"), default=0)),
            "erroMedio": self._as_float(data.get("erroMedio")),
            "erroMaximo": self._as_float(data.get("erroMaximo")),
            "derivaSensor": self._as_float(data.get("derivaSensor")),
            "nomeBuffer": data.get("nomeBuffer", ""),
            "status": str(data.get("status", "")),
            "timestamp": self._as_float(data.get("timestamp"), default=0),
        }
        return row

    def _add_event(self, kind: str, topic: str, payload: str) -> None:
        event = {
            "time": time.strftime("%H:%M:%S"),
            "kind": kind,
            "topic": topic,
            "payload": payload,
        }
        with self._lock:
            self._events.append(event)

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
        self._add_event("erro", topic="dashboard", payload=message)

    @staticmethod
    def _as_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default
