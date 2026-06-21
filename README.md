# Gêmeo Digital — Medidor de pH

Projeto acadêmico que implementa um **gêmeo digital** de um sensor de pH industrial, simulando o ciclo completo de um dispositivo IoT: aquisição de dados no firmware, transmissão via MQTT, processamento em tempo real e visualização em dashboard com manutenção preditiva.

Toda a camada de hardware roda no **Wokwi** (simulador de ESP32 dentro do VS Code), eliminando a necessidade de componentes físicos sem abrir mão da lógica real de firmware em C++.

---

## Objetivos

- Simular o comportamento de degradação de um eletrodo de pH ao longo do tempo
- Rastrear a precisão da leitura comparando o valor medido com soluções tampão de referência (padrões NIST)
- Demonstrar uma arquitetura IoT completa: firmware → MQTT → dashboard
- Implementar manutenção preditiva que projeta quando o sensor precisará de calibração, distinguindo deriva real de ruído transitório

---

## Arquitetura

```
┌─────────────────────────────────┐
│  Wokwi (VS Code Extension)      │
│                                 │
│  ESP32  ←→  LCD I2C             │
│    ↑         LEDs               │
│  Potenciômetro (simula sensor)  │
│                                 │
│  Firmware C++ publica MQTT      │
└──────────────┬──────────────────┘
               │ TCP port 1883
               ▼
        broker.emqx.io
        (broker público)
               │ TCP port 1883
               ▼
┌──────────────────────────────────┐
│  mqtt_bridge.py  (Python)        │
│                                  │
│  paho-mqtt ←→ WebSocket server   │
│  subscreve ph/#    localhost:9001│
└──────────────┬───────────────────┘
               │ WebSocket ws://localhost:9001
               ▼
┌──────────────────────────────────┐
│  dashboard.html  (navegador)     │
│                                  │
│  Gráficos em tempo real          │
│  Manutenção preditiva            │
│  Comandos ao ESP32               │
└──────────────────────────────────┘
```

### Por que o bridge Python é necessário

O navegador não consegue conectar diretamente ao broker externo via WebSocket por dois motivos combinados:

1. **Firewall de rede**: redes universitárias e corporativas bloqueiam conexões WebSocket em portas não-padrão (8000–9999). O MQTT usa porta 1883 para TCP, mas expõe WebSocket em portas alternativas que ficam bloqueadas.
2. **Restrição de origem `file://`**: ao abrir o HTML diretamente do disco, o navegador trata a página como origem única isolada e bloqueia conexões a origens externas.

A solução é o `mqtt_bridge.py`: ele conecta ao broker via **TCP puro** na porta 1883 (não bloqueada para processos Python), e expõe um WebSocket local em `localhost:9001`. O navegador consegue sempre alcançar `localhost` sem restrições de firewall.

---

## Hardware Simulado

| Componente | Pino ESP32 | Função |
|---|---|---|
| Potenciômetro | GPIO 34 (ADC) | Simula o sinal analógico do sensor de pH |
| LCD I2C 16×2 | GPIO 21 (SDA), 22 (SCL) | Exibe leitura local em tempo real |
| LED verde | GPIO 25 | Status OK (erro ≤ 0,05 pH) |
| LED amarelo | GPIO 26 | Status ALERTA (erro ≤ 0,20 pH) |
| LED vermelho | GPIO 27 | Status FALHA (erro > 0,20 pH) |
| Resistores 220 Ω | — | Limitação de corrente dos LEDs |

O potenciômetro ocupa o **GPIO 34** propositalmente: esse pino no ESP32 é exclusivamente de entrada (_input-only_), sem função de saída, o que é a configuração correta para leitura analógica de sensor.

---

## Firmware (`src/main.cpp`)

### Conversão do sinal em pH

O ADC do ESP32 opera com resolução de 12 bits (0–4095). O potenciômetro é mapeado linearmente:

```
pH = 14.0 − (leitura_ADC / 4095) × 14.0
```

O extremo esquerdo do potenciômetro corresponde a pH 14, o extremo direito a pH 0, o centro a pH 7. A leitura é feita como **média de 16 amostras consecutivas** com intervalo de 100 µs entre elas, reduzindo o ruído de quantização do ADC sem necessidade de filtro de hardware.

### Modelo de degradação sintética

A cada amostra, o firmware aplica dois componentes sobre a leitura:

```cpp
derivaSensor += TAXA_DERIVA;            // +0,0002 pH/amostra (acumulativo)
pH += derivaSensor + ruidoFalso(0.015f);
```

- **Deriva** (`derivaSensor`): crescimento linear permanente que simula o envelhecimento do eletrodo. Nunca recua, a não ser por calibração — reflete o fenômeno real de contaminação da membrana.
- **Ruído** (`ruidoFalso`): oscilação aleatória com amplitude ±0,015 pH por amostra, simulando variação térmica e interferência eletromagnética. Usa um gerador linear congruente (LCG) determinístico porque o Wokwi não fornece entropia real de hardware.

A escolha de `TAXA_DERIVA = 0.0002` faz o sensor cruzar o limiar de ALERTA (0,20 pH) após 1000 amostras — com intervalo padrão de 2s, isso corresponde a 33 minutos de operação, tornando a degradação observável em uma sessão de apresentação.

### Soluções tampão de referência

O firmware implementa as três soluções tampão primárias do NIST, usadas em calibração industrial:

| Código | Solução | pH |
|---|---|---|
| `4.0` | Biftalato de potássio | 4,00 |
| `7.0` | Tampão fosfato | 7,00 (padrão) |
| `10.0` | Tampão carbonato/borato | 10,00 |

O buffer ativo define o **valor de referência** contra o qual o erro é calculado a cada amostra. Pode ser trocado remotamente via MQTT durante a operação, sem reiniciar o dispositivo.

### Estatísticas acumuladas

A cada amostra o firmware mantém:

- `erroMedio`: média aritmética de todos os erros absolutos desde a última calibração
- `erroMaximo`: maior erro absoluto já registrado
- `derivaSensor`: valor atual da deriva acumulada (permite ao dashboard reconstruir a velocidade de degradação)

Todos publicados no tópico `ph/estatisticas` como JSON.

### Comandos remotos

| Tópico | Payload | Efeito |
|---|---|---|
| `ph/cmd/calibrar` | qualquer | Zera offset, deriva e estatísticas acumuladas |
| `ph/cmd/buffer` | `"4.0"`, `"7.0"` ou `"10.0"` | Troca a solução tampão ativa |
| `ph/cmd/intervalo` | número em ms (500–60000) | Ajusta o intervalo de amostragem |

### Tópicos MQTT publicados

| Tópico | Conteúdo |
|---|---|
| `ph/leitura` | Valor de pH medido (float, 4 casas decimais) |
| `ph/referencia` | pH da solução tampão ativa |
| `ph/erro` | Desvio com sinal (+/−) |
| `ph/status` | `"OK"`, `"ALERTA"` ou `"FALHA"` |
| `ph/estatisticas` | JSON completo com todas as métricas |
| `ph/evento` | Eventos de ciclo de vida (online, calibrado) |

---

## Bridge MQTT–WebSocket (`streamlit_app/mqtt_bridge.py`)

Roda duas responsabilidades em paralelo:

**Thread MQTT** (paho-mqtt, síncrona):
- Conecta ao `broker.emqx.io:1883` via TCP
- Subscreve ao wildcard `ph/#`
- A cada mensagem recebida, serializa um envelope `{"topic": "...", "payload": "..."}` e agenda o envio no loop asyncio via `run_coroutine_threadsafe`

**Loop asyncio** (WebSocket server):
- Mantém o conjunto de clientes conectados
- Faz broadcast de cada mensagem MQTT para todos os clientes
- Aceita mensagens inversas (comandos do dashboard) e as publica de volta no MQTT

O uso de `asyncio.run_coroutine_threadsafe` é o padrão correto para cruzar a barreira entre o callback síncrono do paho e o loop assíncrono do websockets sem race conditions.

---

## Dashboard (`dashboard.html`)

### Conexão

Usa a API nativa `WebSocket` do navegador para `ws://localhost:9001`. Não usa a biblioteca `mqtt.js` porque o bridge fala WebSocket puro, não MQTT-over-WebSocket — isso simplifica o protocolo e elimina a dependência de biblioteca externa de transporte.

### Erro médio filtrado (`updateConfirmedTrend`)

O valor exibido como "erro médio" na interface usa um algoritmo de confirmação por persistência — não a média bruta do firmware. O problema que ele resolve: o potenciômetro pode ser girado bruscamente pelo usuário, gerando um pico isolado que, incorporado imediatamente à previsão, distorceria o tempo estimado até a falha.

A solução usa dois parâmetros calibrados com base no modelo físico do firmware:

- `NOISE_AMPLITUDE = 0.015` — exatamente a amplitude do `ruidoFalso(0.015f)` do firmware. Uma variação dentro dessa faixa é ruído normal esperado.
- `CONFIRM_STREAK = 3` — amostras consecutivas fora da faixa de ruído necessárias para confirmar que a mudança é real.

Algoritmo:
1. Se a nova leitura está dentro de `trendErr ± NOISE_AMPLITUDE`: atualiza suavemente com média exponencial de peso 90/10
2. Se está fora: conta como candidata (`pendingErr`)
3. Somente após `CONFIRM_STREAK` amostras consecutivas: o valor é atualizado para o novo nível

Resultado: um clique isolado no potenciômetro não contamina a previsão. Uma deriva real é capturada após 3 amostras (~6 segundos com intervalo padrão de 2s).

### Manutenção preditiva

Com o erro médio filtrado e a taxa de deriva, o dashboard calcula:

```
amostras_restantes = (THRESH_WARN − erroMedioFiltrado) / taxa_de_deriva
```

Se o sensor está operando há amostras suficientes, usa a taxa real estimada (`driftAtual / samples`) em vez da constante nominal do firmware.

O gráfico de degradação exibe três camadas:
- **Erro médio** (linha sólida vermelha): histórico do valor filtrado
- **Projeção** (linha tracejada): extensão linear de 8 pontos com base na inclinação dos últimos 10 valores
- **Limite 0,20 pH** (linha pontilhada): onde a falha é declarada

O painel de status sinaliza três níveis: estável (`urgency-low`), calibração em breve (`urgency-medium`, menos de 100 amostras restantes) e falha imediata (`urgency-high`, tendência ou leitura instantânea já no limite).

---

## Como rodar

### Pré-requisitos

- VS Code com extensões **PlatformIO IDE** e **Wokwi Simulator** instaladas
- Licença gratuita do Wokwi ativada (`F1` → `Wokwi: Request a Free License`)
- Python com ambiente virtual em `streamlit_app/.venv`

### 1. Compilar o firmware

Pressione `Ctrl+Alt+B` no VS Code (PlatformIO: Build).  
O firmware vai para `.pio/build/esp32dev/` — o `wokwi.toml` aponta para `firmware.bin` (execução) e `firmware.elf` (depuração).

### 2. Iniciar o bridge

```powershell
streamlit_app\.venv\Scripts\python.exe streamlit_app\mqtt_bridge.py
```

Mantenha essa janela aberta. Saída esperada:

```
[Bridge] WebSocket local em ws://localhost:9001
[MQTT] Conectado ao broker broker.emqx.io (rc=0)
```

### 3. Iniciar o simulador

Abra `diagram.json` no VS Code → `F1` → `Wokwi: Start Simulator`.  
Aguarde no Serial Monitor:

```
[WiFi] Conectado!
[MQTT] Conectado!
[AMOSTRA #1] pH=7.xxx ...
```

### 4. Abrir o dashboard

Abra `dashboard.html` no navegador. O indicador no canto superior direito deve mostrar **"MQTT conectado"** e os dados aparecem imediatamente.

---

## Estrutura de arquivos

```
G-meos-Digitais/
├── src/
│   └── main.cpp              # Firmware do ESP32 (C++ Arduino)
├── streamlit_app/
│   ├── mqtt_bridge.py        # Bridge MQTT ↔ WebSocket
│   ├── requirements.txt      # Dependências Python
│   └── README.md
├── dashboard.html            # Dashboard de visualização
├── diagram.json              # Circuito simulado (Wokwi)
├── platformio.ini            # Configuração de compilação (PlatformIO)
├── wokwi.toml                # Aponta o simulador para o firmware compilado
└── README.md
```

---

## Dependências

**Firmware** (gerenciadas automaticamente pelo PlatformIO via `lib_deps`):
- `knolleary/PubSubClient` — cliente MQTT para Arduino
- `marcoschwartz/LiquidCrystal_I2C` — controle do LCD I2C
- `bblanchon/ArduinoJson` — serialização JSON no ESP32 (v7+)

**Python** (`streamlit_app/requirements.txt`):
- `paho-mqtt >= 2.1` — cliente MQTT TCP
- `websockets >= 12.0` — servidor WebSocket asyncio

**Dashboard** (CDN, sem instalação):
- `Chart.js 4.4.1` — gráficos de linha em tempo real
