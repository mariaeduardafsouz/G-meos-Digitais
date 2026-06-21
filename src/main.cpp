/*
 * ============================================================
 *  Medidor de pH — Gêmeo Digital — Simulação Wokwi
 *  Projeto Acadêmico: Rastreamento de Precisão e Degradação do Sensor
 * ============================================================
 *
 *  Hardware (simulado):
 *    - ESP32 DevKit v1
 *    - Potenciômetro no GPIO 34  → simula sinal analógico do pH
 *    - LCD I2C 16x2 nos GPIO 21/22
 *    - LEDs nos GPIO 25 (verde/OK), 26 (amarelo/ALERTA), 27 (vermelho/FALHA)
 *
 *  Tópicos MQTT publicados:
 *    ph/leitura        → valor bruto de pH do sensor
 *    ph/referencia     → pH esperado da solução tampão em uso
 *    ph/erro           → desvio em relação à referência (precisão)
 *    ph/status         → "OK" | "ALERTA" | "FALHA"
 *    ph/estatisticas   → JSON: { leitura, referencia, erro, erroPct,
 *                                totalAmostras, erroMedio, erroMaximo,
 *                                nomeBuffer, timestamp }
 *
 *  Tópicos MQTT subscritos:
 *    ph/cmd/calibrar   → dispara reset de calibração (payload ignorado)
 *    ph/cmd/buffer     → seleciona a solução tampão ativa:
 *                        "4.0" | "7.0" | "10.0"
 *    ph/cmd/intervalo  → define intervalo de amostragem em ms (ex.: "2000")
 *
 *  Soluções tampão modeladas:
 *    pH 4,00  — Biftalato de potássio
 *    pH 7,00  — Tampão fosfato
 *    pH 10,00 — Tampão carbonato / borato
 *
 *  Limites de precisão:
 *    |erro| <= 0,05  → OK     (LED verde)
 *    |erro| <= 0,20  → ALERTA (LED amarelo)
 *    |erro| >  0,20  → FALHA  (LED vermelho)
 * ============================================================
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoJson.h>
#include <math.h>

// ─── Credenciais Wi-Fi (rede virtual Wokwi) ──────────────────
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// ─── Broker MQTT (broker público de teste) ───────────────────
const char* MQTT_BROKER   = "broker.emqx.io";
const int   MQTT_PORT     = 1883;
const char* MQTT_CLIENT   = "ph_gemeo_digital_esp32";

// ─── Tópicos MQTT ────────────────────────────────────────────
const char* TOPIC_READING   = "ph/leitura";
const char* TOPIC_REFERENCE = "ph/referencia";
const char* TOPIC_ERROR     = "ph/erro";
const char* TOPIC_STATUS    = "ph/status";
const char* TOPIC_STATS     = "ph/estatisticas";
const char* TOPIC_CMD_CAL   = "ph/cmd/calibrar";
const char* TOPIC_CMD_BUF   = "ph/cmd/buffer";
const char* TOPIC_CMD_INT   = "ph/cmd/intervalo";

// ─── Pinos de hardware ───────────────────────────────────────
const int PIN_PH_ANALOG   = 34;
const int PIN_LED_VERDE   = 25;
const int PIN_LED_AMARELO = 26;
const int PIN_LED_VERMELHO= 27;

// ─── Conversão ADC / tensão → pH ─────────────────────────────
const float ADC_MAX       = 4095.0f;
const float VREF          = 3.3f;
const float V_MID         = 1.65f;
const float MV_PER_PH     = 0.05916f;

// ─── Offset de calibração (ajustado pelo comando calibrar) ───
float offsetCalibracao    = 0.0f;

// ─── Soluções tampão: { nome, pH esperado } ──────────────────
struct SolucaoTampao {
  const char* nome;
  float       pH;
};

const SolucaoTampao BUFFERS[] = {
  { "Biftalato  pH 4,0",  4.00f },
  { "Fosfato    pH 7,0",  7.00f },
  { "Carbonato  pH10,0", 10.00f }
};
const int NUM_BUFFERS = 3;
int bufferAtivo       = 1;

// ─── Limites de precisão ─────────────────────────────────────
const float LIMITE_OK     = 0.05f;
const float LIMITE_ALERTA = 0.20f;

// ─── Intervalo de amostragem ─────────────────────────────────
unsigned long intervaloAmostragem = 2000;
unsigned long ultimaAmostra       = 0;

// ─── Estatísticas acumuladas ─────────────────────────────────
unsigned long totalAmostras = 0;
float         somaErro      = 0.0f;
float         erroMaximo    = 0.0f;

// ─── Ruído / deriva simulados ────────────────────────────────
float derivaSensor         = 0.0f;
const float TAXA_DERIVA    = 0.0002f;
unsigned long sementeDrift = 42;

// ─── Objetos ─────────────────────────────────────────────────
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClient        clienteWifi;
PubSubClient      mqtt(clienteWifi);

// ────────────────────────────────────────────────────────────
//  Funções auxiliares
// ────────────────────────────────────────────────────────────

float ruidoFalso(float amplitude) {
  sementeDrift = sementeDrift * 1664525UL + 1013904223UL;
  float r = (float)(sementeDrift & 0xFFFF) / 65535.0f;
  return (r - 0.5f) * 2.0f * amplitude;
}

float lerPH() {
  long soma = 0;
  for (int i = 0; i < 16; i++) {
    soma += analogRead(PIN_PH_ANALOG);
    delayMicroseconds(100);
  }
  float bruto = soma / 16.0f;
  float pH    = 14.0f - (bruto / ADC_MAX) * 14.0f;
  pH += offsetCalibracao;
  derivaSensor += TAXA_DERIVA;
  pH += derivaSensor + ruidoFalso(0.015f);
  pH = constrain(pH, 0.0f, 14.0f);
  return pH;
}

const char* avaliarPrecisao(float erroAbs) {
  digitalWrite(PIN_LED_VERDE,    LOW);
  digitalWrite(PIN_LED_AMARELO,  LOW);
  digitalWrite(PIN_LED_VERMELHO, LOW);

  if (erroAbs <= LIMITE_OK) {
    digitalWrite(PIN_LED_VERDE, HIGH);
    return "OK";
  } else if (erroAbs <= LIMITE_ALERTA) {
    digitalWrite(PIN_LED_AMARELO, HIGH);
    return "ALERTA";
  } else {
    digitalWrite(PIN_LED_VERMELHO, HIGH);
    return "FALHA";
  }
}

void atualizarLCD(float leituraPH, float phRef, const char* status, float erro) {
  const char* statusLCD = (strcmp(status, "ALERTA") == 0) ? "AL" :
                          (strcmp(status, "FALHA")  == 0) ? "FL" : status;
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("pH:");
  lcd.print(leituraPH, 2);
  lcd.print(" Ref:");
  lcd.print(phRef, 1);
  lcd.setCursor(0, 1);
  lcd.print("Err:");
  lcd.print(erro, 3);
  lcd.print(" [");
  lcd.print(statusLCD);
  lcd.print("]");
}

// ────────────────────────────────────────────────────────────
//  Callbacks MQTT
// ────────────────────────────────────────────────────────────

void aoReceberMensagemMQTT(char* topico, byte* payload, unsigned int comprimento) {
  char msg[64] = {0};
  comprimento = min(comprimento, (unsigned int)63);
  memcpy(msg, payload, comprimento);
  msg[comprimento] = '\0';

  Serial.printf("[MQTT] Recebido em '%s': %s\n", topico, msg);

  if (strcmp(topico, TOPIC_CMD_CAL) == 0) {
    offsetCalibracao = 0.0f;
    derivaSensor     = 0.0f;
    totalAmostras    = 0;
    somaErro         = 0.0f;
    erroMaximo       = 0.0f;
    Serial.println("[CAL] Calibracao resetada. Deriva e offset zerados.");
    mqtt.publish("ph/evento", "{\"evento\":\"calibrado\"}");
    return;
  }

  if (strcmp(topico, TOPIC_CMD_BUF) == 0) {
    if (strcmp(msg, "4.0") == 0 || strcmp(msg, "4") == 0) {
      bufferAtivo = 0;
    } else if (strcmp(msg, "7.0") == 0 || strcmp(msg, "7") == 0) {
      bufferAtivo = 1;
    } else if (strcmp(msg, "10.0") == 0 || strcmp(msg, "10") == 0) {
      bufferAtivo = 2;
    } else {
      Serial.printf("[BUF] Buffer desconhecido: %s\n", msg);
      return;
    }
    Serial.printf("[BUF] Buffer ativo → %s\n", BUFFERS[bufferAtivo].nome);
    return;
  }

  if (strcmp(topico, TOPIC_CMD_INT) == 0) {
    long ms = atol(msg);
    if (ms >= 500 && ms <= 60000) {
      intervaloAmostragem = (unsigned long)ms;
      Serial.printf("[INT] Intervalo de amostragem → %lu ms\n", intervaloAmostragem);
    }
    return;
  }
}

// ────────────────────────────────────────────────────────────
//  Conexão Wi-Fi e MQTT
// ────────────────────────────────────────────────────────────

void conectarWiFi() {
  Serial.print("[WiFi] Conectando a ");
  Serial.print(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED && tentativas < 30) {
    delay(500);
    Serial.print(".");
    tentativas++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Conectado! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Falhou — operando offline.");
  }
}

void conectarMQTT() {
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(aoReceberMensagemMQTT);

  Serial.print("[MQTT] Conectando a ");
  Serial.print(MQTT_BROKER);

  int tentativas = 0;
  while (!mqtt.connected() && tentativas < 5) {
    Serial.print(".");
    if (mqtt.connect(MQTT_CLIENT)) {
      Serial.println("\n[MQTT] Conectado!");
      mqtt.subscribe(TOPIC_CMD_CAL);
      mqtt.subscribe(TOPIC_CMD_BUF);
      mqtt.subscribe(TOPIC_CMD_INT);
      mqtt.publish("ph/evento", "{\"evento\":\"online\",\"dispositivo\":\"ph_gemeo_digital\"}");
    } else {
      Serial.printf(" falhou (rc=%d)\n", mqtt.state());
      delay(2000);
    }
    tentativas++;
  }
}

// ────────────────────────────────────────────────────────────
//  setup()
// ────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  Serial.println("\n==============================");
  Serial.println("  pH Gemeo Digital — Iniciando");
  Serial.println("==============================");

  pinMode(PIN_LED_VERDE,    OUTPUT);
  pinMode(PIN_LED_AMARELO,  OUTPUT);
  pinMode(PIN_LED_VERMELHO, OUTPUT);
  digitalWrite(PIN_LED_VERDE,    LOW);
  digitalWrite(PIN_LED_AMARELO,  LOW);
  digitalWrite(PIN_LED_VERMELHO, LOW);

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);

  Wire.begin(21, 22);
  Wire.setClock(100000);
  lcd.init();
  lcd.backlight();
  lcd.display();
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("pH Gemeo Digital");
  lcd.setCursor(0, 1);
  lcd.print("Inicializando...");

  conectarWiFi();
  conectarMQTT();

  lcd.clear();
  lcd.print("Sistema Pronto");
  lcd.setCursor(0, 1);
  lcd.print("Buffer: pH ");
  lcd.print(BUFFERS[bufferAtivo].pH, 1);

  delay(1500);
  Serial.println("[SETUP] Concluido. Iniciando loop de medicao.");
  Serial.println("Buffer ativo: " + String(BUFFERS[bufferAtivo].nome));
  Serial.println("Intervalo de amostragem: " + String(intervaloAmostragem) + " ms\n");
}

// ────────────────────────────────────────────────────────────
//  loop()
// ────────────────────────────────────────────────────────────

void loop() {
  if (!mqtt.connected()) {
    conectarMQTT();
  }
  mqtt.loop();

  unsigned long agora = millis();
  if (agora - ultimaAmostra >= intervaloAmostragem) {
    ultimaAmostra = agora;

    float leituraPH = lerPH();
    float phRef     = BUFFERS[bufferAtivo].pH;
    float erro      = leituraPH - phRef;
    float erroAbs   = fabs(erro);
    float erroPct   = (erroAbs / phRef) * 100.0f;

    totalAmostras++;
    somaErro += erroAbs;
    if (erroAbs > erroMaximo) erroMaximo = erroAbs;
    float erroMedio = somaErro / totalAmostras;

    const char* status = avaliarPrecisao(erroAbs);

    atualizarLCD(leituraPH, phRef, status, erro);

    Serial.printf(
      "[AMOSTRA #%lu] pH=%.3f | Ref=%.2f | Err=%+.3f (%.2f%%) | Status=%s | "
      "ErroMedio=%.3f | ErroMax=%.3f | Deriva=%.4f\n",
      totalAmostras, leituraPH, phRef, erro, erroPct,
      status, erroMedio, erroMaximo, derivaSensor
    );

    char buf[32];

    snprintf(buf, sizeof(buf), "%.4f", leituraPH);
    mqtt.publish(TOPIC_READING, buf);

    snprintf(buf, sizeof(buf), "%.2f", phRef);
    mqtt.publish(TOPIC_REFERENCE, buf);

    snprintf(buf, sizeof(buf), "%+.4f", erro);
    mqtt.publish(TOPIC_ERROR, buf);

    mqtt.publish(TOPIC_STATUS, status);

    JsonDocument doc;
    doc["leitura"]       = round(leituraPH * 1000.0f) / 1000.0f;
    doc["referencia"]    = phRef;
    doc["erro"]          = round(erro * 10000.0f) / 10000.0f;
    doc["erroPct"]       = round(erroPct * 100.0f) / 100.0f;
    doc["totalAmostras"] = totalAmostras;
    doc["erroMedio"]     = round(erroMedio * 10000.0f) / 10000.0f;
    doc["erroMaximo"]    = round(erroMaximo * 10000.0f) / 10000.0f;
    doc["derivaSensor"]  = round(derivaSensor * 10000.0f) / 10000.0f;
    doc["nomeBuffer"]    = BUFFERS[bufferAtivo].nome;
    doc["status"]        = status;
    doc["timestamp"]     = agora;

    char jsonBuf[256];
    serializeJson(doc, jsonBuf, sizeof(jsonBuf));
    mqtt.publish(TOPIC_STATS, jsonBuf);
  }
}
