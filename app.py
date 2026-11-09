"""Manopla cardíaca – simulador web (Streamlit).

Requer manopla_cardiaca.py na mesma pasta.
Rodar:  streamlit run app.py
Apenas demonstração; não use para decisões clínicas.
"""
import time

import matplotlib.pyplot as plt
import streamlit as st

from manopla_cardiaca import Sim, Config, P

WINDOW = 120  # minutos visíveis nos gráficos

st.set_page_config(page_title="Manopla cardíaca – simulador", layout="wide")
ss = st.session_state

# ---------- estado inicial ----------
if "sim" not in ss:
    ss.sim = Sim()
    ss.playing = True
    ss.last_wall = time.time()


def sync():
    """Copia os valores dos controles para o simulador."""
    sim = ss.sim
    sim.cfg.activity = ss.ac
    sim.cfg.target = ss.tg
    sim.cfg.lo = ss.lo
    sim.cfg.hi = ss.hi
    sim.auto = ss.mode == "Automático"


# ---------- callbacks ----------
def do_inject(kind, key):
    sync()
    ss.sim.inject(kind, ss[key], "manual:")


def do_spike():
    ss.sim.stress_spike()


def do_toggle():
    ss.playing = not ss.playing


def do_reset():
    sync()
    ss.sim = Sim(cfg=ss.sim.cfg, auto=ss.sim.auto)


# ---------- barra lateral ----------
with st.sidebar:
    st.header("Aplicação")
    st.slider("Dose de betabloqueador (mg)", .5, 10.0, 2.0, .5, key="db")
    st.button("Injetar betabloqueador", on_click=do_inject, args=("b", "db"),
              use_container_width=True, type="primary")
    st.slider("Dose de estimulante (mg)", .5, 10.0, 2.0, .5, key="ds")
    st.button("Injetar estimulante", on_click=do_inject, args=("s", "ds"),
              use_container_width=True)

    st.header("Controlador")
    st.radio("Modo", ["Manual", "Automático"], key="mode", horizontal=True)
    st.slider("Alvo de batimentos (bpm)", 50, 100, 65, key="tg")
    st.slider("Limite seguro inferior (bpm)", 40, 70, 50, key="lo")
    st.slider("Limite seguro superior (bpm)", 80, 140, 100, key="hi")

    st.header("Paciente")
    st.slider("Atividade / estresse (%)", 0, 100, 20, key="ac")
    st.button("Pico de estresse", on_click=do_spike, use_container_width=True)
    st.slider("Velocidade (min simulados por segundo)", 1, 30, 5, key="sp")
    c1, c2 = st.columns(2)
    c1.button("Pausar" if ss.playing else "Retomar", on_click=do_toggle,
              use_container_width=True)
    c2.button("Reiniciar", on_click=do_reset, use_container_width=True)

    st.caption(
        f"Intertravamentos: dose máxima de {P['max_dose']} mg, intervalo mínimo "
        f"de {P['min_gap']} min, limite de {P['cap']} mg por sessão e bloqueio "
        "do betabloqueador abaixo do limite inferior.")

# ---------- cabeçalho ----------
st.title("Manopla cardíaca: simulador de controle de batimentos")
st.caption("Modelo fictício (unidades abstratas) de farmacocinética com "
           "betabloqueador e estimulante. Aplique doses manualmente ou deixe "
           "o controlador automático minimizar os mg dentro da faixa segura.")


def plot(sim):
    x0 = max(0.0, sim.t - WINDOW)
    pts = [p for p in sim.h if p[0] >= x0]
    ts = [p[0] for p in pts]
    fig, (a1, a2) = plt.subplots(
        2, 1, figsize=(9, 6), sharex=True,
        gridspec_kw=dict(height_ratios=[3, 1.3]))
    a1.axhspan(sim.cfg.lo, sim.cfg.hi, color="tab:green", alpha=.12)
    a1.axhline(sim.cfg.target, color="tab:green", ls="--", lw=1)
    a1.plot(ts, [p[1] for p in pts], color="tab:red", lw=1.8)
    for t, kind in sim.doses:
        if t >= x0:
            a1.plot(t, 156, marker="v",
                    color="tab:blue" if kind == "b" else "tab:orange")
    a1.set_ylim(30, 160)
    a1.set_ylabel("Batimentos (bpm)")
    a1.grid(alpha=.25)
    a2.plot(ts, [p[2] for p in pts], color="tab:blue", label="betabloqueador")
    a2.plot(ts, [p[3] for p in pts], color="tab:orange", label="estimulante")
    a2.set_ylim(0, 2)
    a2.set_ylabel("Concentração (u.a.)")
    a2.set_xlabel("Tempo (min)")
    a2.set_xlim(x0, x0 + WINDOW)
    a2.grid(alpha=.25)
    a2.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return fig


@st.fragment(run_every=0.5)
def view():
    sync()
    sim = ss.sim

    # avança a simulação conforme o tempo real decorrido
    now = time.time()
    elapsed = min(1.0, now - ss.last_wall)
    ss.last_wall = now
    if ss.playing:
        remaining = elapsed * ss.sp
        while remaining > 0:
            d = min(.05, remaining)
            sim.tick(d)
            remaining -= d

    mean = sim.total / sim.cnt if sim.cnt else None
    out = 100 * sim.out_t / sim.cnt if sim.cnt else 0
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Batimentos agora", f"{round(sim.hr)} bpm", sim.state_label(),
              delta_color="off")
    k2.metric("Média de bpm", f"{mean:.1f}" if mean else "–")
    k3.metric("Total aplicado", f"{sim.mg:.1f} mg", f"{sim.n} aplicações",
              delta_color="off")
    k4.metric("Tempo fora da faixa", f"{out:.0f}%",
              f"{sim.t:.0f} min simulados", delta_color="off")

    if sim.msg:
        st.warning(sim.msg)

    fig = plot(sim)
    st.pyplot(fig)
    plt.close(fig)
    st.caption("Linha vermelha: batimentos. Faixa verde: limites seguros. "
               "Tracejado: alvo. Azul: betabloqueador. Laranja: estimulante.")

    with st.expander("Registro de eventos", expanded=True):
        st.text("\n".join(reversed(sim.messages[-10:])) or "Sem eventos ainda.")


view()
