#!/usr/bin/env python3
"""Manopla cardíaca – simulador (versão Python).

Modelo fictício (unidades abstratas) de farmacocinética com betabloqueador
e estimulante. Portado do simulador HTML/JS original.

Exemplos:
    python manopla_cardiaca.py --minutes 240 --auto --spike 60 --spike 150
    python manopla_cardiaca.py --minutes 120 --dose 10:b:3 --dose 40:s:2
    python manopla_cardiaca.py --auto --minutes 300 --plot --out resultado.png

Apenas demonstração; não use para decisões clínicas.
"""
from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, field

# Parâmetros do modelo
P = dict(kb=.03, ks=.05, ke=.15, Vb=5, Vs=8, ec=1, eb=.38, es=.30,
         max_dose=10, min_gap=3, cap=60)


@dataclass
class Config:
    """Equivalente aos sliders do painel."""
    activity: float = 20      # atividade / estresse (%)
    target: float = 65        # alvo de batimentos
    lo: float = 50            # limite seguro inferior
    hi: float = 100           # limite seguro superior


@dataclass
class Sim:
    cfg: Config = field(default_factory=Config)
    auto: bool = False
    t: float = 0.0
    cb: float = 0.0           # betabloqueador no plasma
    ceb: float = 0.0          # betabloqueador no efeito
    cs: float = 0.0           # estimulante no plasma
    ces: float = 0.0          # estimulante no efeito
    hr: float = 72.0
    h: list = field(default_factory=list)       # histórico (t, hr, b, s)
    doses: list = field(default_factory=list)   # (t, tipo)
    mg: float = 0.0
    n: int = 0
    total: float = 0.0        # soma hr*dt
    cnt: float = 0.0
    out_t: float = 0.0
    last: float = -99.0
    next_decision: float = 0.0
    spike: float = 0.0
    messages: list = field(default_factory=list)  # log de eventos
    msg: str = ""

    # ---------- modelo ----------
    def hr0(self) -> float:
        return 60 + 60 * self.cfg.activity / 100 + self.spike

    @staticmethod
    def effect(ceb, ces, base):
        return (base * (1 - P['eb'] * ceb / (P['ec'] + ceb))
                * (1 + P['es'] * ces / (P['ec'] + ces)))

    @staticmethod
    def _step(s, dt):
        """s: dict com cb, cs, ceb, ces (modificado in-place)."""
        s['cb'] -= P['kb'] * s['cb'] * dt
        s['cs'] -= P['ks'] * s['cs'] * dt
        s['ceb'] += P['ke'] * (s['cb'] - s['ceb']) * dt
        s['ces'] += P['ke'] * (s['cs'] - s['ces']) * dt

    def predict(self, dose, kind, horizon=30):
        s = dict(cb=self.cb, cs=self.cs, ceb=self.ceb, ces=self.ces)
        base = self.hr0()
        if kind == 'b':
            s['cb'] += dose / P['Vb']
        else:
            s['cs'] += dose / P['Vs']
        mn, total, k = 1e9, 0.0, 0
        t = 0.0
        while t < horizon:
            self._step(s, .5)
            h = self.effect(s['ceb'], s['ces'], base)
            mn = min(mn, h)
            total += h
            k += 1
            t += .5
        return dict(min=mn, mean=total / k)

    # ---------- ações ----------
    def log(self, text):
        self.messages.append(f"t={self.t:.0f} min: {text}")

    def inject(self, kind, dose, src="manual:") -> bool:
        if self.t - self.last < P['min_gap']:
            self.msg = (f"Intertravamento: aguarde "
                        f"{P['min_gap'] - (self.t - self.last):.1f} min.")
            return False
        if self.mg + dose > P['cap']:
            self.msg = "Intertravamento: limite da sessão atingido."
            return False
        if kind == 'b' and self.hr <= self.cfg.lo + 2:
            self.msg = "Bloqueio: batimentos próximos do limite inferior."
            return False
        if kind == 'b':
            self.cb += dose / P['Vb']
        else:
            self.cs += dose / P['Vs']
        self.mg += dose
        self.n += 1
        self.last = self.t
        self.doses.append((self.t, kind))
        self.msg = ""
        nome = "betabloqueador" if kind == 'b' else "estimulante"
        self.log(f"{src} {dose} mg de {nome}")
        return True

    def stress_spike(self):
        self.spike += 35
        self.log("pico de estresse")

    # ---------- controlador automático ----------
    def controller(self):
        if self.t < self.next_decision or self.t - self.last < P['min_gap']:
            return
        self.next_decision = self.t + 2
        lo, tg, tol = self.cfg.lo, self.cfg.target, 3
        floor = lo + 3
        none = self.predict(0, 'b')

        if none['min'] < floor or self.hr < lo + 2:
            d = .5
            while d <= P['max_dose']:
                if self.predict(d, 's')['min'] >= floor:
                    self.inject('s', d, "auto:")
                    return
                d += .5
            self.inject('s', P['max_dose'], "auto:")
            return

        if none['mean'] > tg + tol and self.hr > tg + tol:
            best = 0.0
            d = .5
            while d <= P['max_dose']:
                p = self.predict(d, 'b')
                if p['min'] < floor:
                    break
                best = d
                if p['mean'] <= tg + tol:
                    break
                d += .5
            if best > 0:
                self.inject('b', best, "auto:")

    # ---------- passo de simulação ----------
    def tick(self, dt):
        s = dict(cb=self.cb, cs=self.cs, ceb=self.ceb, ces=self.ces)
        self._step(s, dt)
        self.cb, self.cs, self.ceb, self.ces = s['cb'], s['cs'], s['ceb'], s['ces']
        self.spike *= math.exp(-dt / 6)

        target = self.effect(self.ceb, self.ces, self.hr0())
        self.hr += ((target - self.hr) * (1 - math.exp(-dt / .6))
                    + (random.random() - .5) * .25)
        self.t += dt
        self.total += self.hr * dt
        self.cnt += dt
        if self.hr < self.cfg.lo or self.hr > self.cfg.hi:
            self.out_t += dt

        if (int(math.floor(self.t * 20 + .5)) % 10 == 0 or not self.h
                or self.t - self.h[-1][0] >= .5):
            self.h.append((self.t, self.hr, self.ceb, self.ces))
        if len(self.h) > 1200:
            self.h.pop(0)

        if self.auto:
            self.controller()

    # ---------- estatísticas ----------
    def state_label(self) -> str:
        lo, hi = self.cfg.lo, self.cfg.hi
        if self.hr < lo:
            return "Bradicardia"
        if self.hr > hi:
            return "Taquicardia"
        if self.hr < lo + 5 or self.hr > hi - 5:
            return "Perto do limite"
        return "Normal"

    def summary(self) -> str:
        mean = self.total / self.cnt if self.cnt else float('nan')
        out = 100 * self.out_t / self.cnt if self.cnt else 0
        return (f"Batimentos finais : {self.hr:.0f} bpm ({self.state_label()})\n"
                f"Média de bpm      : {mean:.1f}\n"
                f"Total aplicado    : {self.mg:.1f} mg em {self.n} aplicações\n"
                f"Fora da faixa     : {out:.0f}%\n"
                f"Tempo simulado    : {self.t:.0f} min")


# ---------- execução / CLI ----------
def run(sim: Sim, minutes, dt=.05, spikes=(), doses=()):
    """doses: lista de (tempo, 'b'|'s', mg)."""
    spikes = sorted(spikes)
    doses = sorted(doses)
    while sim.t < minutes:
        while spikes and sim.t >= spikes[0]:
            spikes.pop(0)
            sim.stress_spike()
        while doses and sim.t >= doses[0][0]:
            _, kind, mg = doses.pop(0)
            if not sim.inject(kind, mg, "manual:"):
                sim.log(sim.msg)
        sim.tick(dt)


def plot(sim: Sim, out=None):
    import matplotlib.pyplot as plt
    ts = [p[0] for p in sim.h]
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True,
                                 gridspec_kw=dict(height_ratios=[3, 1.3]))
    a1.axhspan(sim.cfg.lo, sim.cfg.hi, color='tab:green', alpha=.12,
               label='faixa segura')
    a1.axhline(sim.cfg.target, color='tab:green', ls='--', label='alvo')
    a1.plot(ts, [p[1] for p in sim.h], color='tab:red', lw=1.8, label='bpm')
    for t, kind in sim.doses:
        if ts and t >= ts[0]:
            a1.plot(t, 158, marker='v',
                    color='tab:blue' if kind == 'b' else 'tab:orange')
    a1.set_ylim(30, 160)
    a1.set_ylabel('Frequência cardíaca (bpm)')
    a1.legend(loc='upper right')
    a2.plot(ts, [p[2] for p in sim.h], color='tab:blue', label='betabloqueador')
    a2.plot(ts, [p[3] for p in sim.h], color='tab:orange', label='estimulante')
    a2.set_ylim(0, 2)
    a2.set_ylabel('Concentração (u.a.)')
    a2.set_xlabel('Tempo (min)')
    a2.legend(loc='upper right')
    fig.tight_layout()
    if out:
        fig.savefig(out, dpi=130)
        print(f"Gráfico salvo em {out}")
    else:
        plt.show()


def parse_dose(txt):
    t, kind, mg = txt.split(':')
    if kind not in ('b', 's'):
        raise argparse.ArgumentTypeError("tipo deve ser 'b' ou 's'")
    return float(t), kind, float(mg)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--minutes', type=float, default=240, help='duração simulada')
    ap.add_argument('--auto', action='store_true', help='controlador automático')
    ap.add_argument('--target', type=float, default=65, help='alvo de bpm (50-100)')
    ap.add_argument('--lo', type=float, default=50, help='limite inferior (40-70)')
    ap.add_argument('--hi', type=float, default=100, help='limite superior (80-140)')
    ap.add_argument('--activity', type=float, default=20, help='atividade/estresse %% (0-100)')
    ap.add_argument('--spike', type=float, action='append', default=[],
                    metavar='MIN', help='pico de estresse no minuto MIN (repetível)')
    ap.add_argument('--dose', type=parse_dose, action='append', default=[],
                    metavar='MIN:TIPO:MG', help="dose manual, ex.: 10:b:3 (b=betabloq., s=estimulante)")
    ap.add_argument('--dt', type=float, default=.05, help='passo de simulação (min)')
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--plot', action='store_true', help='mostra gráfico (matplotlib)')
    ap.add_argument('--out', help='salva o gráfico neste arquivo (implica --plot)')
    a = ap.parse_args()

    if a.seed is not None:
        random.seed(a.seed)
    sim = Sim(cfg=Config(a.activity, a.target, a.lo, a.hi), auto=a.auto)
    run(sim, a.minutes, a.dt, a.spike, a.dose)

    print("\n".join(sim.messages))
    print("-" * 40)
    print(sim.summary())
    if a.plot or a.out:
        plot(sim, a.out)


if __name__ == '__main__':
    main()
