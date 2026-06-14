from __future__ import annotations

import html
import time
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mqtt_service import MqttTelemetryService


LIMITE_OK = 0.05
LIMITE_ALERTA = 0.20
PLOT_TEXT_COLOR = "#102016"
PLOT_MUTED_COLOR = "#46564b"
PLOT_GRID_COLOR = "#dfe8dd"
PLOT_AXIS_COLOR = "#9fb2a5"


st.set_page_config(
    page_title="Gemeo Digital pH",
    page_icon="pH",
    layout="wide",
)


st.markdown(
    """
    <style>
      .stApp {
        background: #f6f9f4;
      }

      .block-container {
        padding-top: 1.35rem;
        padding-bottom: 2rem;
        max-width: 1280px;
      }

      [data-testid="stSidebar"] {
        background: #062b1a;
      }

      [data-testid="stSidebar"] h1,
      [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] p {
        color: #f4fbf1;
      }

      .dashboard-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        padding: 0.35rem 0 1.1rem;
      }

      .eyebrow {
        color: #5f6f64;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0;
        text-transform: uppercase;
      }

      .dashboard-header h1 {
        margin: 0.12rem 0 0;
        color: #102016;
        font-size: 2rem;
        line-height: 1.1;
      }

      .dashboard-header p {
        margin: 0.35rem 0 0;
        color: #66766b;
      }

      .header-pill {
        min-width: 190px;
        border: 1px solid #dfe8dd;
        border-radius: 999px;
        background: #ffffff;
        color: #20372a;
        padding: 0.72rem 1rem;
        text-align: center;
        font-weight: 700;
        box-shadow: 0 8px 24px rgba(18, 34, 24, 0.06);
      }

      .header-pill.connected {
        background: #07351f;
        border-color: #07351f;
        color: #f4fff5;
      }

      .header-pill.waiting {
        background: #fff7d6;
        border-color: #f1d77a;
        color: #6f5200;
      }

      .kpi-card {
        height: 132px;
        border: 1px solid #dfe8dd;
        border-radius: 8px;
        background: #ffffff;
        padding: 0.9rem 0.95rem;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 10px 26px rgba(18, 34, 24, 0.055);
      }

      .kpi-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.7rem;
      }

      .metric-title {
        color: #24392b;
        font-size: 0.86rem;
        font-weight: 800;
      }

      .metric-badge {
        border-radius: 999px;
        padding: 0.18rem 0.5rem;
        font-size: 0.72rem;
        font-weight: 800;
        background: #edf4e8;
        color: #12351f;
      }

      .metric-value {
        color: #102016;
        font-size: 1.85rem;
        line-height: 1.05;
        font-weight: 800;
      }

      .metric-caption {
        color: #6d7b70;
        font-size: 0.78rem;
        font-weight: 600;
      }

      .kpi-card.ok {
        background: #07351f;
        border-color: #07351f;
      }

      .kpi-card.ok .metric-title,
      .kpi-card.ok .metric-value,
      .kpi-card.ok .metric-caption {
        color: #f4fff5;
      }

      .kpi-card.ok .metric-badge {
        background: #a9e934;
        color: #07351f;
      }

      .kpi-card.alerta {
        background: #fff2bf;
        border-color: #e7c453;
      }

      .kpi-card.alerta .metric-title,
      .kpi-card.alerta .metric-value {
        color: #5d4300;
      }

      .kpi-card.alerta .metric-caption {
        color: #7c640e;
      }

      .kpi-card.alerta .metric-badge {
        background: #e2b100;
        color: #2d2100;
      }

      .kpi-card.falha {
        background: #ffe0df;
        border-color: #e58a86;
      }

      .kpi-card.falha .metric-title,
      .kpi-card.falha .metric-value {
        color: #7b1715;
      }

      .kpi-card.falha .metric-caption {
        color: #99403d;
      }

      .kpi-card.falha .metric-badge {
        background: #c92d27;
        color: #fff7f7;
      }

      .section-title {
        color: #20372a;
        font-size: 1rem;
        font-weight: 800;
        margin: 0.4rem 0 0.7rem;
      }

      .status-box {
        border: 1px solid #dfe8dd;
        border-radius: 8px;
        background: #ffffff;
        padding: 1rem;
        box-shadow: 0 10px 26px rgba(18, 34, 24, 0.055);
      }

      .status-box strong {
        display: block;
        color: #20372a;
        font-size: 0.96rem;
        margin-bottom: 0.35rem;
      }

      .muted {
        color: #6b7280;
      }

      .stPlotlyChart {
        border: 1px solid #dfe8dd;
        border-radius: 8px;
        background: #ffffff;
        padding: 0.35rem 0.45rem;
        box-shadow: 0 10px 26px rgba(18, 34, 24, 0.055);
      }
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


def format_signed_float(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):+.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def status_tone(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "ok":
        return "ok"
    if normalized == "alerta":
        return "alerta"
    if normalized == "falha":
        return "falha"
    return "neutral"


def status_label(status: str) -> str:
    return (status or "sem dados").upper()


def status_caption(status: str) -> str:
    tone = status_tone(status)
    if tone == "ok":
        return "Dentro do limite de precisao"
    if tone == "alerta":
        return "Proximo do limite de erro"
    if tone == "falha":
        return "Fora da tolerancia definida"
    return "Aguardando dados MQTT"


def metric_card(title: str, value: str, caption: str = "", tone: str = "neutral", badge: str = "") -> None:
    badge_html = ""
    if badge:
        badge_html = f"<span class='metric-badge'>{html.escape(badge)}</span>"

    st.markdown(
        f"""
        <div class="kpi-card {html.escape(tone)}">
          <div class="kpi-head">
            <span class="metric-title">{html.escape(title)}</span>
            {badge_html}
          </div>
          <div class="metric-value">{html.escape(value)}</div>
          <div class="metric-caption">{html.escape(caption)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_panel(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="status-box">
          <strong>{html.escape(title)}</strong>
          <span class="muted">{html.escape(body)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def ph_axis_range(df: pd.DataFrame) -> list[float]:
    values = pd.concat([df["leitura"], df["referencia"]], ignore_index=True).dropna()
    if values.empty:
        return [0, 14]

    lower = max(0.0, float(values.min()) - 0.35)
    upper = min(14.0, float(values.max()) + 0.35)
    if upper - lower < 0.8:
        middle = (upper + lower) / 2
        lower = max(0.0, middle - 0.4)
        upper = min(14.0, middle + 0.4)
    return [lower, upper]


def chart_axis(title: str = "", axis_range: list[float] | None = None) -> dict[str, Any]:
    axis = {
        "title": {"text": title, "font": {"color": PLOT_TEXT_COLOR, "size": 13}},
        "tickfont": {"color": PLOT_MUTED_COLOR, "size": 12},
        "gridcolor": PLOT_GRID_COLOR,
        "linecolor": PLOT_AXIS_COLOR,
        "tickcolor": PLOT_AXIS_COLOR,
        "zeroline": False,
        "showline": True,
        "ticks": "outside",
    }
    if axis_range is not None:
        axis["range"] = axis_range
    return axis


def chart_legend() -> dict[str, Any]:
    return {
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "right",
        "x": 1,
        "font": {"color": PLOT_TEXT_COLOR, "size": 12},
        "bgcolor": "rgba(255,255,255,0.9)",
    }


def draw_ph_chart(df: pd.DataFrame) -> None:
    y_range = ph_axis_range(df)
    baseline = [y_range[0]] * len(df)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=baseline,
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["leitura"],
            mode="lines",
            name="pH medido",
            fill="tonexty",
            fillcolor="rgba(169, 233, 52, 0.28)",
            line=dict(color="#9bdc2f", width=3, shape="spline"),
            hovertemplate="pH medido: %{y:.3f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["referencia"],
            mode="lines",
            name="Valor base do tampao",
            line=dict(color="#f3b244", width=3, shape="spline"),
            hovertemplate="Valor base: %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        height=360,
        margin=dict(l=18, r=18, t=18, b=18),
        yaxis=chart_axis("pH", y_range),
        xaxis=chart_axis(),
        legend=chart_legend(),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=PLOT_GRID_COLOR, font=dict(color=PLOT_TEXT_COLOR)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color=PLOT_TEXT_COLOR),
    )
    st.plotly_chart(fig, use_container_width=True)


def draw_error_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["erro"],
            mode="lines",
            name="Erro",
            line=dict(color="#2f7f66", width=3, shape="spline"),
            hovertemplate="Erro: %{y:+.4f}<extra></extra>",
        )
    )
    fig.add_hline(y=LIMITE_OK, line_dash="dot", line_color="#68ad2e", annotation_text="+OK")
    fig.add_hline(y=-LIMITE_OK, line_dash="dot", line_color="#68ad2e", annotation_text="-OK")
    fig.add_hline(y=LIMITE_ALERTA, line_dash="dash", line_color="#c92d27", annotation_text="+Falha")
    fig.add_hline(y=-LIMITE_ALERTA, line_dash="dash", line_color="#c92d27", annotation_text="-Falha")
    fig.update_annotations(font=dict(color=PLOT_TEXT_COLOR, size=12), bgcolor="rgba(255,255,255,0.82)")
    fig.update_layout(
        height=320,
        margin=dict(l=18, r=18, t=18, b=18),
        yaxis=chart_axis("Erro (pH)"),
        xaxis=chart_axis(),
        legend=chart_legend(),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=PLOT_GRID_COLOR, font=dict(color=PLOT_TEXT_COLOR)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color=PLOT_TEXT_COLOR),
    )
    st.plotly_chart(fig, use_container_width=True)


def draw_degradation_chart(df: pd.DataFrame) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["derivaSensor"],
            mode="lines",
            name="Deriva",
            line=dict(color="#f3b244", width=2.5, shape="spline"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["erroMedio"],
            mode="lines",
            name="Erro medio",
            line=dict(color="#2f7f66", width=2.5, shape="spline"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["tempo"],
            y=df["erroMaximo"],
            mode="lines",
            name="Erro maximo",
            line=dict(color="#c92d27", width=2.5, shape="spline"),
        )
    )
    fig.update_layout(
        height=320,
        margin=dict(l=18, r=18, t=18, b=18),
        yaxis=chart_axis("pH"),
        xaxis=chart_axis(),
        legend=chart_legend(),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=PLOT_GRID_COLOR, font=dict(color=PLOT_TEXT_COLOR)),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color=PLOT_TEXT_COLOR),
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
status = str(latest.get("status", ""))
tone = status_tone(status)
last_seen = snapshot["last_seen"]
last_seen_text = time.strftime("%H:%M:%S", time.localtime(last_seen)) if last_seen else "-"
mqtt_state = "Conectado" if snapshot["connected"] else "Conectando"
mqtt_pill_class = "connected" if snapshot["connected"] else "waiting"

st.markdown(
    f"""
    <div class="dashboard-header">
      <div>
        <div class="eyebrow">Gemeo Digital</div>
        <h1>Medidor de pH</h1>
        <p>Telemetria MQTT em tempo real comparando o pH medido com a solucao tampao.</p>
      </div>
      <div class="header-pill {mqtt_pill_class}">MQTT {html.escape(mqtt_state)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(f"Assinando `{snapshot['stats_topic']}` em `{snapshot['broker']}:{snapshot['port']}`")

top_cards = st.columns(4)
with top_cards[0]:
    metric_card(
        "pH atual",
        format_float(latest.get("leitura")),
        status_caption(status),
        tone=tone,
        badge=status_label(status),
    )
with top_cards[1]:
    metric_card(
        "Valor base",
        format_float(latest.get("referencia"), 2),
        str(latest.get("nomeBuffer") or "Solucao tampao"),
    )
with top_cards[2]:
    metric_card("Erro atual", format_signed_float(latest.get("erro"), 4), "Diferenca entre pH real e base")
with top_cards[3]:
    metric_card("Amostras", str(int(latest.get("totalAmostras", 0))) if latest else "0", f"Ultima: {last_seen_text}")

bottom_cards = st.columns(4)
with bottom_cards[0]:
    metric_card("Erro medio", format_float(latest.get("erroMedio"), 4), "Media acumulada do erro")
with bottom_cards[1]:
    metric_card("Erro maximo", format_float(latest.get("erroMaximo"), 4), "Maior desvio observado")
with bottom_cards[2]:
    metric_card("Deriva", format_float(latest.get("derivaSensor"), 4), "Deslocamento sintetico do sensor")
with bottom_cards[3]:
    metric_card("Broker", mqtt_state, f"{snapshot['broker']}:{snapshot['port']}")

status_panel("Saude da conexao", snapshot["last_error"] or "Sem erros recentes.")

control_col, prediction_col = st.columns([1, 1])

with control_col:
    st.markdown("<div class='section-title'>Comandos remotos</div>", unsafe_allow_html=True)
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
    st.markdown("<div class='section-title'>Manutencao preditiva</div>", unsafe_allow_html=True)
    prediction = estimate_maintenance(df)
    status_panel("Estimativa", prediction["message"])
    if prediction.get("samples_remaining") is not None:
        metric_card("Amostras restantes", str(prediction["samples_remaining"]), "Ate atingir o limite de alerta")
    st.caption("Estimativa simples baseada na tendencia do erro maximo das ultimas amostras.")

if df.empty:
    st.warning("Aguardando dados MQTT. Inicie a simulacao no Wokwi e confirme que o Serial Monitor publica amostras.")
else:
    chart_col1, chart_col2 = st.columns([2, 1])
    with chart_col1:
        st.markdown("<div class='section-title'>pH medido x valor base da solucao tampao</div>", unsafe_allow_html=True)
        draw_ph_chart(df)
    with chart_col2:
        st.markdown("<div class='section-title'>Erro de medicao</div>", unsafe_allow_html=True)
        draw_error_chart(df)

    st.markdown("<div class='section-title'>Degradacao sintetica</div>", unsafe_allow_html=True)
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
