#!/usr/bin/env python3
"""
Ponte MQTT <-> WebSocket local.
Conecta ao broker externo via TCP (paho-mqtt) e serve um
WebSocket em localhost:9001 para o dashboard HTML.

Uso:
    python mqtt_bridge.py
"""
import asyncio
import json
import paho.mqtt.client as mqtt
import websockets

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT   = 1883
TOPIC_SUB   = "ph/#"
WS_HOST     = "localhost"
WS_PORT     = 9001

_clients: set = set()
_mqttc = None
_loop  = None


def _on_connect(client, userdata, flags, rc, props=None):
    print(f"[MQTT] Conectado ao broker {MQTT_BROKER} (rc={rc})")
    client.subscribe(TOPIC_SUB)

def _on_disconnect(client, userdata, flags, rc, props=None):
    print(f"[MQTT] Desconectado (rc={rc})")

def _on_message(client, userdata, msg):
    envelope = json.dumps({
        "topic":   msg.topic,
        "payload": msg.payload.decode(errors="replace"),
    })
    if _loop:
        asyncio.run_coroutine_threadsafe(_broadcast(envelope), _loop)

async def _broadcast(data: str):
    dead = set()
    for ws in list(_clients):
        try:
            await ws.send(data)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)

async def _ws_handler(websocket):
    _clients.add(websocket)
    print(f"[WS] Dashboard conectado ({len(_clients)} cliente(s))")
    try:
        async for raw in websocket:
            try:
                cmd = json.loads(raw)
                topic   = cmd.get("topic", "")
                payload = cmd.get("payload", "")
                if _mqttc and topic:
                    _mqttc.publish(topic, payload, qos=0)
                    print(f"[WS->MQTT] {topic}: {payload}")
            except Exception as e:
                print(f"[WS] Mensagem inválida: {e}")
    except Exception:
        pass
    finally:
        _clients.discard(websocket)
        print(f"[WS] Dashboard desconectado ({len(_clients)} cliente(s))")

async def main():
    global _loop, _mqttc
    _loop = asyncio.get_running_loop()

    _mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    _mqttc.on_connect    = _on_connect
    _mqttc.on_disconnect = _on_disconnect
    _mqttc.on_message    = _on_message
    _mqttc.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    _mqttc.loop_start()

    print(f"[Bridge] WebSocket local em ws://{WS_HOST}:{WS_PORT}")
    print(f"[Bridge] Aguardando dados de {MQTT_BROKER}:{MQTT_PORT} ...")
    async with websockets.serve(_ws_handler, WS_HOST, WS_PORT):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
