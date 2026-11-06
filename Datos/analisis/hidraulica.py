"""Los caudales de cada modulo: inventario, etiquetado y balance.

Topologia declarada por el usuario (2026-09-01), que por fin ASIGNA cada tag a
una corriente del diagrama -- la pregunta que quedo abierta en
ANALISIS_ENSAYOS_2026-08-30.md 4.1:

  desarenador  --> Q_des    (M2_SENSOR_FLUJO_DA / M3_SENSOR_CAUDAL_PARSHALL)
       |  se reparte en dos
       +--> directo al tanque de aireacion
       +--> UASB --> tanque de aireacion
  tanque de lodos --> Q_rec (M2_SENSOR_CAUDAL12IN / M3_SENSOR_CAUDAL12IN)
  tanque de aireacion --> clarificadores --> efluente + tanque de lodos

Es decir: Q_des es UNA sola medida aguas arriba del reparto, no dos. Al tanque
de aireacion entra Q_des (por los dos caminos) + Q_rec, y sale Q_des + Q_rec si
el volumen es constante. No hay medidor en la salida del tanque.

CAUDALIMETRO_SALIDA y CAUDALIMETRO_ENTRADA son de la PTAR completa.
"""
import numpy as np
import pandas as pd

# corriente fisica -> tag del historiador
CORRIENTES = {
    'M2': {'Q_des': 'M2_SENSOR_FLUJO_DA', 'Q_rec': 'M2_SENSOR_CAUDAL12IN'},
    'M3': {'Q_des': 'M3_SENSOR_CAUDAL_PARSHALL', 'Q_rec': 'M3_SENSOR_CAUDAL12IN'},
}
PLANTA = ['CAUDALIMETRO_SALIDA'] + \
         ['CAUDALIMETRO_ENTRADA[%d]' % i for i in range(4)] + \
         ['CAUDALIMETRO_BYPASS[%d]' % i for i in range(4)]


def diagnostico(h):
    """Salud de cada tag de caudal. Un caudal de aguas residuales sano tiene
    ciclo diario; si no lo tiene, o vive en cero o pegado al tope, no mide."""
    filas = []
    tags = [(m, c, t) for m, d in CORRIENTES.items() for c, t in d.items()] + \
           [('PTAR', t.split('[')[0].replace('CAUDALIMETRO_', '').lower(), t) for t in PLANTA]
    for mod, cor, tag in tags:
        if tag not in h:
            continue
        v = pd.to_numeric(h[tag], errors='coerce')
        v = v.where((v > -1e3) & (v < 1e4))          # basura de escala del historiador
        vv = v.dropna()
        if len(vv) == 0:
            filas.append(dict(modulo=mod, corriente=cor, tag=tag, n=0)); continue
        tope = vv.quantile(.999)
        viva = vv[vv > 0.5]
        ciclo = viva.groupby(viva.index.hour).median() if len(viva) > 500 else pd.Series(dtype=float)
        amp = 100 * (ciclo.max() - ciclo.min()) / ciclo.median() if len(ciclo) > 12 else np.nan
        filas.append(dict(
            modulo=mod, corriente=cor, tag=tag, n=len(vv),
            pct_cero=100 * (vv < 0.5).mean(), pct_tope=100 * (vv > 0.98 * tope).mean(),
            distintos=vv.nunique(), mediana=viva.median() if len(viva) else np.nan,
            p05=viva.quantile(.05) if len(viva) else np.nan,
            p95=viva.quantile(.95) if len(viva) else np.nan,
            amp_diaria_pct=amp,
            h_min=ciclo.idxmin() if len(ciclo) > 12 else np.nan,
            h_max=ciclo.idxmax() if len(ciclo) > 12 else np.nan,
            desde=vv[vv > 0.5].index.min() if (vv > 0.5).any() else pd.NaT,
            hasta=vv[vv > 0.5].index.max() if (vv > 0.5).any() else pd.NaT))
    d = pd.DataFrame(filas)
    d['util'] = (d.n > 1000) & (d.pct_tope < 5) & (d.pct_cero < 50) & (d.amp_diaria_pct > 10)
    return d


def series(h, mod):
    """Q_des, Q_rec y su suma para un modulo, con ceros como NaN."""
    q = pd.DataFrame({c: pd.to_numeric(h[t], errors='coerce')
                      for c, t in CORRIENTES[mod].items() if t in h})
    q = q.where((q > 0.5) & (q < 1e4))
    q['Q_in'] = q.get('Q_des', np.nan) + q.get('Q_rec', np.nan)   # entra al tanque
    q['R_rec'] = q.get('Q_rec', np.nan) / q.get('Q_des', np.nan)  # razon de recirculacion
    return q


def salida_planta(h):
    s = pd.to_numeric(h['CAUDALIMETRO_SALIDA'], errors='coerce')
    return s.where((s > 0.5) & (s < 1e4))


def corr_por_agregacion(a, b, retardos=range(0, 9)):
    """Correlacion en tres niveles de agregacion, barriendo el retardo.

    hora a hora | media de cada dia | perfil medio de 24 h.
    El signo puede invertirse entre niveles: ver ANALISIS_ENSAYOS 4.2.
    """
    out = []
    for L in retardos:
        j = pd.DataFrame({'a': a.shift(L), 'b': b}).dropna()
        if len(j) < 200:
            continue
        dia = j.groupby(j.index.date).mean()
        per = j.groupby(j.index.hour).mean()
        out.append(dict(retardo_h=L, n=len(j),
                        r_hora=j.a.corr(j.b),
                        r_dia=dia.a.corr(dia.b) if len(dia) > 10 else np.nan,
                        r_perfil=per.a.corr(per.b) if len(per) > 12 else np.nan))
    return pd.DataFrame(out)


def balance(q, qsal, mod):
    """Contraste entre lo que entra a un modulo y lo que sale de la PTAR.

    No es un balance cerrado: qsal es de la planta completa (3 modulos). Sirve
    para ver si la escala y el ciclo diario son coherentes.
    """
    j = pd.DataFrame({'Q_des': q.Q_des, 'Q_rec': q.Q_rec,
                      'Q_in': q.Q_in, 'Q_sal_ptar': qsal}).dropna(how='all')
    per = j.groupby(j.index.hour).median()
    return dict(
        n=len(j.dropna()),
        med_des=j.Q_des.median(), med_rec=j.Q_rec.median(), med_in=j.Q_in.median(),
        med_sal=j.Q_sal_ptar.median(),
        razon_des_sal=j.Q_des.median() / j.Q_sal_ptar.median(),
        razon_rec_des=j.Q_rec.median() / j.Q_des.median(),
        perfil=per)
