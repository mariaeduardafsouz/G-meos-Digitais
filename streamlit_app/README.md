# Bridge MQTT–WebSocket

Script Python que conecta o broker MQTT externo ao dashboard HTML via WebSocket local.

## Por que existe

O navegador não consegue conectar diretamente ao broker `broker.emqx.io` porque redes com firewall bloqueiam as portas WebSocket do MQTT (8000–9999), e abrir o HTML via `file://` adiciona restrições de origem. O `mqtt_bridge.py` resolve isso: conecta ao broker via TCP (porta 1883, não bloqueada) e expõe um WebSocket em `localhost:9001` que o navegador sempre alcança.

## Como rodar

Com o ambiente virtual já criado:

```powershell
streamlit_app\.venv\Scripts\python.exe streamlit_app\mqtt_bridge.py
```

Para criar o ambiente virtual pela primeira vez:

```powershell
python -m venv streamlit_app\.venv
streamlit_app\.venv\Scripts\python -m pip install -r streamlit_app\requirements.txt
```

Pacotes instalados: `paho-mqtt >= 2.1` e `websockets >= 12.0`.

## Saída esperada

```
[Bridge] WebSocket local em ws://localhost:9001
[Bridge] Aguardando dados de broker.emqx.io:1883 ...
[MQTT] Conectado ao broker broker.emqx.io (rc=0)
[WS] Dashboard conectado (1 cliente(s))
```

## Configuração

| Variável | Valor padrão | Descrição |
|---|---|---|
| `MQTT_BROKER` | `broker.emqx.io` | Broker público compartilhado |
| `MQTT_PORT` | `1883` | TCP — não WebSocket |
| `TOPIC_SUB` | `ph/#` | Subscreve todos os tópicos do projeto |
| `WS_HOST` | `localhost` | Endereço do WebSocket local |
| `WS_PORT` | `9001` | Porta do WebSocket local |
