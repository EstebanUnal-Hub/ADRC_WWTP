"""Los ensayos de identificacion trazados desde el PLC ctrlX.

A diferencia del historiador del SCADA, la traza del ctrlX SI registra la senal
de control: el tag `HMI.Soplador_1_Consigna` es la consigna de 0 a 100 % que el
PLC manda al variador, muestreada a 50 ms. Eso convierte estos archivos en la
unica fuente de datos entrada-salida en las unidades correctas.

Los archivos son ventanas deslizantes del buffer de traza (500 s cada una, con
solape); hay que unirlas por sello de tiempo y quitar duplicados. El sello es
tiempo de marcha del PLC en ms, no hora de reloj: para fechar un ensayo se
compara la trayectoria de OD contra el historico del SCADA (`fechar`).

Carpetas, en Simulaciones/PTAR/01 Datos/:
  data2/        41 min, escalon 0 -> 95 %  -- fechado: M1, 2026-03-12 16:27
  datosIdent2/  109 min, escalera 35/50/75/100 % con dos sopladores -- sin fechar
  otros/        dos sesiones sueltas, OD ya alto y sensores muy discrepantes
"""
import glob
import os

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'Simulaciones', 'PTAR', '01 Datos')

# Saturacion de oxigeno en Tunja: 2.820 m sobre el nivel del mar, ~0,72 atm.
# El valor exacto depende de temperatura y salinidad; se usa como rango.
SSAT = (5.5, 7.0)


def cargar(carpeta):
    """Une las ventanas de traza de una carpeta en una sola serie, indexada en s."""
    partes = []
    for f in glob.glob(os.path.join(BASE, carpeta, '*.csv')):
        x = pd.read_csv(f, sep=r'\s+', skiprows=2, engine='python', na_values=['""'])
        x.columns = [c.replace('HMI.', '').replace('PLC_PRG.', '') for c in x.columns]
        partes.append(x)
    d = pd.concat(partes, ignore_index=True).sort_values('Timestamp(ms)')
    d = d.drop_duplicates(subset='Timestamp(ms)')
    d = d.set_index(d['Timestamp(ms)'] / 1000.0).drop(columns='Timestamp(ms)')
    d.index.name = 't_s'
    return d.dropna(subset=['OxigenoPromedio'])


def consigna(d):
    """Consigna efectiva de cada soplador, en % de su propio rango."""
    u1 = d.Soplador_1_Consigna * d.Soplador_1_CmdEncender.ffill().fillna(1)
    u2 = pd.Series(0.0, index=d.index)
    if 'rSignalPrueba2' in d and 'Soplador_2_CmdEncender' in d:
        u2 = d.rSignalPrueba2 * d.Soplador_2_CmdEncender.fillna(0)
    return u1, u2


def tramos(d, min_s=120):
    """Segmenta por consigna constante y resume cada tramo."""
    u1, u2 = consigna(d)
    corte = ((u1.diff().abs() > 0.5) | (u2.diff().abs() > 0.5)).cumsum()
    filas = []
    for _, g in d.groupby(corte):
        dur = g.index[-1] - g.index[0]
        if dur < min_s:
            continue
        t = g.index.to_numpy()
        y = g.OxigenoPromedio.to_numpy()
        filas.append(dict(t0=t[0], dur_s=dur, u1=u1.loc[t[0]], u2=u2.loc[t[0]],
                          od_ini=y[:40].mean(), od_fin=y[-40:].mean(),
                          od_med=y.mean(), pend_h=np.polyfit(t, y, 1)[0] * 3600))
    return pd.DataFrame(filas)


def _foptd(t, y0, dy, tau, theta):
    z = np.clip((t - theta) / max(tau, 1e-6), 0, None)
    return y0 + dy * (1 - np.exp(-z)) * (t >= theta)


def ajustar_escalon(d, t_ini=None, t_fin=None):
    """Primer orden con retardo sobre el arranque, con u en % de consigna.

    Devuelve tambien K y b0 en unidades del PLC, que es lo que el bloque de
    funcion del ADRC va a recibir, y KLa: en el modelo
    dS/dt = KLa (Ssat - S) - r el polo es exactamente -KLa, asi que la constante
    de tiempo del ajuste da KLa sin necesidad de conocer Ssat.
    """
    u1, _ = consigna(d)
    g = d.loc[t_ini:t_fin]
    t = g.index.to_numpy()
    y = g.OxigenoPromedio.to_numpy()
    uu = u1.loc[g.index].to_numpy()
    t0 = t[np.argmax(uu > 1)]
    m = t >= t0
    t, y = t[m] - t0, y[m]
    U = float(np.median(uu[m]))
    p, _ = curve_fit(_foptd, t, y, p0=[y[0], y[-1] - y[0], 300, 10], maxfev=40000,
                     bounds=([-1, 0, 10, 0], [3, 10, 5000, 300]))
    res = y - _foptd(t, *p)
    r2 = 1 - (res ** 2).sum() / ((y - y.mean()) ** 2).sum()
    tau_h = p[2] / 3600
    KLa = 1 / tau_h
    return dict(u=U, y0=p[0], dy=p[1], tau_min=p[2] / 60, theta_s=p[3], r2=r2,
                K=p[1] / U, b0=p[1] / U / tau_h, KLa=KLa,
                r_min=KLa * (SSAT[0] - (p[0] + p[1])),
                r_max=KLa * (SSAT[1] - (p[0] + p[1])),
                t=t, y=y, yhat=_foptd(t, *p))


def fechar(d, ox, modulos=('M1', 'M2', 'M3'), n_mejores=3):
    """Fecha un ensayo comparando su trayectoria de OD contra el SCADA.

    Los dos sensores por separado discriminan mucho mejor que el promedio. Solo
    es concluyente si el ensayo tiene una excursion grande: una traza plana casa
    con cualquier rato tranquilo del historico.
    """
    pat = d[['Oxigeno_1', 'Oxigeno_2']].copy()
    pat.index = pd.to_timedelta(pat.index, unit='s')
    pat = pat.resample('1min').mean().dropna().to_numpy()
    n = len(pat)
    out = []
    for mod in modulos:
        s = ox[[mod + '_od1', mod + '_od2']].resample('1min').mean()
        A = s.to_numpy()
        err = np.full(len(A), np.nan)
        for i in range(len(A) - n):
            W = A[i:i + n]
            if np.isnan(W).mean() > 0.02:
                continue
            err[i] = np.nanmean((W - pat) ** 2)
        orden = np.argsort(np.where(np.isnan(err), 1e9, err))
        elegidos = []
        for i in orden:
            if not np.isfinite(err[i]):
                break
            if all(abs(i - j) > 180 for j in elegidos):
                elegidos.append(i)
            if len(elegidos) >= n_mejores:
                break
        for i in elegidos:
            W = A[i:i + n]
            m = np.isfinite(W).all(axis=1)
            out.append(dict(modulo=mod, inicio=s.index[i], rmse=np.sqrt(err[i]),
                            corr1=np.corrcoef(W[m, 0], pat[m, 0])[0, 1],
                            corr2=np.corrcoef(W[m, 1], pat[m, 1])[0, 1]))
    return pd.DataFrame(out).sort_values('rmse').reset_index(drop=True)


def informe(ox=None):
    """Resumen de los tres conjuntos de traza."""
    A = {}
    for c in ('data2', 'datosIdent2', 'otros'):
        d = cargar(c)
        A[c] = dict(d=d, tramos=tramos(d))
        print('== %s: %d muestras, %.1f min' % (c, len(d), (d.index.max() - d.index.min()) / 60))
        print(A[c]['tramos'].round(3).to_string(index=False))
    f = ajustar_escalon(A['data2']['d'])          # ventana completa, 41 min
    A['data2']['ajuste'] = f
    print('\n== data2, escalon 0 -> %.0f %% de consigna' % f['u'])
    print('   tau %.1f min | retardo %.0f s | R2 %.4f' % (f['tau_min'], f['theta_s'], f['r2']))
    print('   K  = %.5f mg/L por punto de consigna' % f['K'])
    print('   b0 = %.4f mg/L/(%%·h)   <- en unidades del PLC, sin conversion' % f['b0'])
    print('   KLa = %.2f 1/h  ->  respiracion %.0f a %.0f mg/(L·h) segun Ssat %.1f-%.1f'
          % (f['KLa'], f['r_min'], f['r_max'], *SSAT))
    return A
