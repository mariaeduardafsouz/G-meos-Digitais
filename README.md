# Gemeos Digitais - Medidor de pH

Projeto de gemeo digital para um medidor de pH simulado no Wokwi Web, com
telemetria via MQTT e dashboard em Streamlit.

## Estrutura atual

```text
Gemeos_Digitais/
+-- sketch.ino                 # Firmware Arduino usado no Wokwi Web
+-- diagram.json               # Circuito do Wokwi
+-- libraries.txt              # Bibliotecas usadas pelo Wokwi
+-- streamlit_app/
|   +-- app.py                  # Dashboard Streamlit
|   +-- mqtt_service.py         # Cliente MQTT do dashboard
|   +-- requirements.txt        # Dependencias Python
|   +-- README.md               # Instrucoes especificas do Streamlit
+-- README.md
+-- .gitignore
```

## Como rodar o Wokwi no navegador

1. Abra o projeto no Wokwi Web.
2. Copie o conteudo de `sketch.ino` para a aba `sketch.ino` do Wokwi.
3. Copie o conteudo de `diagram.json` para a aba `diagram.json` do Wokwi.
4. Copie o conteudo de `libraries.txt` para a aba `libraries.txt` do Wokwi.
5. Clique em Start Simulation.

O ESP32 deve conectar ao Wi-Fi simulado do Wokwi, conectar ao broker MQTT e
publicar as leituras nos topicos `ph/#`.

## Como rodar o dashboard Streamlit

No terminal, dentro desta pasta:

```powershell
.\.venv\Scripts\python -m streamlit run streamlit_app\app.py
```

Se a `.venv` nao existir, crie e instale as dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r streamlit_app\requirements.txt
.\.venv\Scripts\python -m streamlit run streamlit_app\app.py
```

Depois abra:

```text
http://localhost:8501
```

## Conexao MQTT

O fluxo esperado e:

```text
Wokwi/ESP32 -> broker MQTT -> Streamlit
```

Configuracao padrao:

```text
Broker: broker.hivemq.com
Porta: 1883
Prefixo de topico: ph
```

Topicos principais publicados pelo ESP32:

```text
ph/leitura
ph/referencia
ph/erro
ph/status
ph/estatisticas
ph/evento
```

Topicos de comando usados pelo Streamlit:

```text
ph/cmd/buffer
ph/cmd/calibrar
ph/cmd/intervalo
```

## Observacoes

O broker HiveMQ publico e compartilhado. Para apresentacao ou testes ele serve
bem, mas em um projeto real o ideal e usar um broker privado ou um prefixo de
topico unico para evitar conflito com outros usuarios.
