from __future__ import annotations

import time
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mqtt_service import MqttTelemetryService


LIMITE_OK = 0.05
LIMITE_ALERTA = 0.20


st.set_page_config(
    page_title="Gemeo Digital pH",
    page_icon="pH",
    layout="wide",
)


st.markdown(
    """
    <style>
      .status-box {
        border-radius: 6px;
        padding: 0.8rem 1rem;
        font-weight: 700;
        text-align: center;
        border: 1px solid rgba(49, 51, 63, 0.2);
      }
      .status-ok { background: #d8f3dc; color: #1b5e20; }
      .status-alerta { background: #fff3bf; color: #7c5a00; }
      .status-falha { background: #ffd6d6; color: #8a1c1c; }
      .muted { color: #6b7280; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_mqtt_service(broker: str, port: int, topic_prefix: str, max_samples: int) -> MqttTelemetryService:
    service = MqttTelemetryService(
        broker=broker,
        port=port,
        topic_prefix=topic_prefix,
        max_samples=max_samples,
    )
    service.start()
    return service


def format_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def status_class(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "ok":
        return "status-ok"
    if normalized == "alerta":
        return "status-alerta"
    return "status-falha"


def status_label(status: str) -> str:
    return (status or "sem dados").upper()


def build_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "received_at" in df:
        df["tempo"] = pd.to_datetime(df["received_at"], unit="s")
    return df


def estimate_maintenance(df: pd.DataFrame, limit: float = LIMITE_ALERTA) -> dict[str, Any]:
    if df.empty or "totalAmostras" not in df or "erroMaximo" not in df:
        return {"state": "empty", "message": "Aguardando telemetria suficiente."}

    current = float(df["erroMaximo"].iloc[-1])
    samples = int(df["totalAmostras"].iloc[-1])
    if current >= limit:
        return {
            "state": "reached",
            "message": f"Limite de {limit:.2f} pH ja foi atingido.",
            "samples_remaining": 0,
        }

    tail = df[["totalAmostras", "erroMaximo"]].dropna().tail(30)
    if len(tail) < 5:
        return {"state": "warming", "message": "Coletando mais amostras para estimar tendencia."}

    x = tail["totalAmostras"].astype(float).to_list()
    y = tail["erroMaximo"].astype(float).to_list()
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator == 0:
        return {"state": "flat", "message": "Ainda nao ha variacao suficiente para prever manutencao."}

    slope = sum((xv - x_mean) * (yv - y_mean) for xv, yv in zip(x, y)) / denominator
    if slope <= 0:
        return {"state": "flat", "message": "Erro maximo estavel; sem previsao de falha crescente."}

    samples_remaining = max(0, int((limit - current) / slope))
    return {
        "state": "predicted",
        "message": f"Previsao: limite de {limit:.2f} pH em cerca de {samples_remaining} amostras.",
        "samples_remaining": samples_remaining,
        "target_sample": samples + samples_remaining,
    }


def draw_ph_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["tempo"], y=df["leitura"], mode="lines", name="pH medido"))
    fig.add_trace(go.Scatter(x=df["tempo"], y=df["referencia"], mode="lines", name="Referencia"))
    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=30, b=20),
        yaxis_title="pH",
        xaxis_title="Tempo",
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def draw_error_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["tempo"], y=df["erro"], mode="lines", name="Erro"))
    fig.add_hline(y=LIMITE_OK, line_dash="dot", line_color="#2e7d32", annotation_text="+OK")
    fig.add_hline(y=-LIMITE_OK, line_dash="dot", line_color="#2e7d32", annotation_text="-OK")
    fig.add_hline(y=LIMITE_ALERTA, line_dash="dash", line_color="#c62828", annotation_text="+Falha")
    fig.add_hline(y=-LIMITE_ALERTA, line_dash="dash", line_color="#c62828", annotation_text="-Falha")
    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=30, b=20),
        yaxis_title="Erro (pH)",
        xaxis_title="Tempo",
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


def draw_degradation_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["tempo"], y=df["derivaSensor"], mode="lines", name="Deriva"))
    fig.add_trace(go.Scatter(x=df["tempo"], y=df["erroMedio"], mode="lines", name="Erro medio"))
    fig.add_trace(go.Scatter(x=df["tempo"], y=df["erroMaximo"], mode="lines", name="Erro maximo"))
    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=30, b=20),
        yaxis_title="pH",
        xaxis_title="Tempo",
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig, use_container_width=True)


with st.sidebar:
    st.header("Conexao MQTT")
    broker = st.text_input("Broker", value="broker.hivemq.com")
    port = st.number_input("Porta", min_value=1, max_value=65535, value=1883, step=1)
    topic_prefix = st.text_input("Prefixo dos topicos", value="ph")
    max_samples = st.number_input("Historico maximo", min_value=100, max_value=10000, value=1000, step=100)
    refresh_seconds = st.slider("Atualizacao da tela (s)", min_value=1, max_value=10, value=2)
    auto_refresh = st.checkbox("Atualizar automaticamente", value=True)

service = get_mqtt_service(broker, int(port), topic_prefix, int(max_samples))
snapshot = service.snapshot()
df = build_dataframe(snapshot["rows"])
latest = df.iloc[-1].to_dict() if not df.empty else {}

st.title("Gemeo Digital - Medidor de pH")
st.caption(
    f"Assinando `{snapshot['stats_topic']}` em `{snapshot['broker']}:{snapshot['port']}`"
)

conn_col, seen_col, error_col = st.columns([1, 1, 2])
conn_col.metric("MQTT", "Conectado" if snapshot["connected"] else "Conectando")
last_seen = snapshot["last_seen"]
seen_col.metric("Ultima amostra", time.strftime("%H:%M:%S", time.localtime(last_seen)) if last_seen else "-")
error_col.info(snapshot["last_error"] or "Sem erros recentes.")

st.divider()

metric_cols = st.columns(6)
metric_cols[0].metric("pH atual", format_float(latest.get("leitura")))
metric_cols[1].metric("Referencia", format_float(latest.get("referencia"), 2))
metric_cols[2].metric("Erro", format_float(latest.get("erro"), 4))
metric_cols[3].metric("Deriva", format_float(latest.get("derivaSensor"), 4))
metric_cols[4].metric("Erro medio", format_float(latest.get("erroMedio"), 4))
metric_cols[5].metric("Amostras", str(int(latest.get("totalAmostras", 0))) if latest else "0")

status = str(latest.get("status", ""))
st.markdown(
    f"<div class='status-box {status_class(status)}'>STATUS: {status_label(status)}</div>",
    unsafe_allow_html=True,
)

st.divider()

control_col, prediction_col = st.columns([1, 1])

with control_col:
    st.subheader("Comandos remotos")
    buffer_value = st.selectbox("Solucao tampao ativa", ["4.0", "7.0", "10.0"], index=1)
    if st.button("Enviar buffer", use_container_width=True):
        service.publish_buffer(buffer_value)
        st.success(f"Comando enviado: buffer {buffer_value}")

    interval_ms = st.number_input("Intervalo de amostragem (ms)", min_value=500, max_value=60000, value=2000, step=500)
    if st.button("Enviar intervalo", use_container_width=True):
        service.publish_interval(int(interval_ms))
        st.success(f"Comando enviado: intervalo {int(interval_ms)} ms")

    if st.button("Calibrar sensor", use_container_width=True):
        service.publish_calibration()
        service.clear()
        st.success("Comando de calibracao enviado.")

with prediction_col:
    st.subheader("Manutencao preditiva")
    prediction = estimate_maintenance(df)
    st.write(prediction["message"])
    if prediction.get("samples_remaining") is not None:
        st.metric("Amostras restantes", prediction["samples_remaining"])
    st.caption("Estimativa simples baseada na tendencia do erro maximo das ultimas amostras.")

st.divider()

if df.empty:
    st.warning("Aguardando dados MQTT. Inicie a simulacao no Wokwi e confirme que o Serial Monitor publica amostras.")
else:
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.subheader("pH em tempo real")
        draw_ph_chart(df)
    with chart_col2:
        st.subheader("Erro de medicao")
        draw_error_chart(df)

    st.subheader("Degradacao sintetica")
    draw_degradation_chart(df)

    with st.expander("Ultimas amostras"):
        cols = [
            "received_time",
            "leitura",
            "referencia",
            "erro",
            "erroPct",
            "erroMedio",
            "erroMaximo",
            "derivaSensor",
            "status",
            "nomeBuffer",
            "totalAmostras",
        ]
        st.dataframe(df[cols].tail(50), use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Baixar historico CSV",
            data=csv,
            file_name="historico_ph.csv",
            mime="text/csv",
        )

with st.expander("Eventos MQTT"):
    events = pd.DataFrame(snapshot["events"])
    if events.empty:
        st.caption("Nenhum evento registrado ainda.")
    else:
        st.dataframe(events.tail(50), use_container_width=True)

if auto_refresh:
    time.sleep(refresh_seconds)
    st.rerun()
