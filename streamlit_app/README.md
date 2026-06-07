# Dashboard Streamlit - Gemeo Digital pH

Este app consome os dados MQTT publicados pelo ESP32 no Wokwi e oferece uma
interface para acompanhamento do gemeo digital do sensor de pH.

## Como rodar

Crie e ative um ambiente virtual, instale as dependencias e inicie o Streamlit:

```powershell
cd C:\Users\KABUM\Documents\Playground\Gemeos_Digitais
python -m venv .venv
.\.venv\Scripts\python -m pip install -r streamlit_app\requirements.txt
.\.venv\Scripts\python -m streamlit run streamlit_app\app.py
```

Depois abra a URL exibida pelo Streamlit, normalmente:

```text
http://localhost:8501
```

## Fluxo esperado

1. Inicie a simulacao no Wokwi.
2. O firmware publica em `ph/estatisticas`.
3. O dashboard assina `ph/#` no broker `broker.hivemq.com`.
4. Use os controles do dashboard para enviar comandos:

```text
ph/cmd/buffer
ph/cmd/calibrar
ph/cmd/intervalo
```

## Observacao

O broker HiveMQ publico e compartilhado. Para um projeto em producao, use um
prefixo de topico unico ou um broker privado.
