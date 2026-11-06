"""Ganancia y constante de tiempo del lazo de oxigeno, por regresion ARX.

Por que ARX y no ajuste de escalones. El ajuste escalon a escalon
(escalones.py) necesita que el operario deje quieta la consigna el tiempo
suficiente y que la respuesta se asiente dentro de la ventana; eso descarta el
95 % del registro y sesga hacia los escalones grandes. La regresion

    y[k+1] = phi*y[k] + gamma*u[k] + delta

usa TODA la ventana, informe o no, y da los mismos dos numeros:

    tau = -Ts / ln(phi)          K = gamma / (1 - phi)

que son la constante de tiempo y la ganancia estatica incremental del modelo
continuo equivalente dy/dt = (K*u - y)/tau. La ganancia asi obtenida es
INCREMENTAL y local, de modo que no la contamina la realimentacion del
operario (que sesga la caracteristica estatica; ver ANALISIS_SCADA 3.4).

Se valida cada ventana simulando el modelo en lazo abierto desde y[0] con la u
real (R2 de simulacion libre, no de prediccion a un paso, que siempre sale
optimista con Ts << tau).
"""
import numpy as np
import pandas as pd


def arx1(y, u, extra=None, ts_min=1.0):
    """Ajusta y[k+1] = phi*y[k] + gamma*u[k] + delta (+ theta'*extra[k]).

    Devuelve tau [min], K [unidad de y por unidad de u], y el R2 de simulacion.
    """
    y = np.asarray(y, float); u = np.asarray(u, float)
    n = len(y)
    if n < 20:
        return None
    X = [y[:-1], u[:-1], np.ones(n - 1)]
    ne = 0
    if extra is not None:
        E = np.atleast_2d(np.asarray(extra, float))
        if E.shape[0] != n:
            E = E.T
        for j in range(E.shape[1]):
            X.append(E[:-1, j]); ne += 1
    X = np.column_stack(X)
    Y = y[1:]
    if not np.isfinite(X).all() or not np.isfinite(Y).all():
        return None
    try:
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    phi, gamma, delta = beta[0], beta[1], beta[2]
    if not (0.0 < phi < 0.99999):
        return None
    tau = -ts_min / np.log(phi)
    K = gamma / (1 - phi)
    # simulacion libre: el unico criterio honesto de calidad
    ys = np.empty(n); ys[0] = y[0]
    for k in range(n - 1):
        ys[k + 1] = phi * ys[k] + gamma * u[k] + delta + \
                    (X[k, 3:] @ beta[3:] if ne else 0.0)
    ss = ((y - y.mean()) ** 2).sum()
    r2 = 1 - ((y - ys) ** 2).sum() / ss if ss > 0 else np.nan
    out = dict(phi=phi, tau=tau, K=K, delta=delta, r2_sim=r2, n=n,
               std_u=u.std(), rango_y=np.ptp(y), y_med=y.mean(), u_med=u.mean())
    if ne:
        out['coef_extra'] = beta[3:]
    return out


def barrido(y, u, extra=None, ventana=180, paso=60, ts_min=1.0,
            std_u_min=5.0, rango_y_min=0.2, r2_min=0.5,
            tau_lim=(1.0, 300.0)):
    """Ventanas deslizantes sobre una serie continua. Una fila por ventana valida."""
    d = pd.concat([y.rename('y'), u.rename('u')], axis=1)
    if extra is not None:
        d = d.join(extra)
    cols_e = [c for c in d.columns if c not in ('y', 'u')]
    out = []
    # solo tramos sin huecos: se corta donde falta cualquier columna
    ok = d.notna().all(axis=1)
    bloque = (~ok).cumsum()
    for _, g in d[ok].groupby(bloque[ok]):
        if len(g) < ventana:
            continue
        # exige rejilla regular dentro del bloque
        for i in range(0, len(g) - ventana + 1, paso):
            w = g.iloc[i:i + ventana]
            dt = np.diff(w.index.to_numpy()).astype('timedelta64[s]').astype(float)
            if len(dt) and (dt.max() > ts_min * 60 * 1.5):
                continue
            if w.u.std() < std_u_min or np.ptp(w.y.to_numpy()) < rango_y_min:
                continue
            r = arx1(w.y.to_numpy(), w.u.to_numpy(),
                     w[cols_e].to_numpy() if cols_e else None, ts_min)
            if r is None or not np.isfinite(r['r2_sim']) or r['r2_sim'] < r2_min:
                continue
            if not (tau_lim[0] <= r['tau'] <= tau_lim[1]):
                continue
            r['inicio'] = w.index[0]
            out.append(r)
    return pd.DataFrame(out)


def resumen(t, etiqueta='', cols=('tau', 'K')):
    """Mediana e intervalo intercuartil de cada parametro."""
    if t is None or len(t) == 0:
        return dict(etiqueta=etiqueta, n=0)
    r = dict(etiqueta=etiqueta, n=len(t), r2_med=t.r2_sim.median())
    for c in cols:
        r[c + '_p50'] = t[c].median()
        r[c + '_p25'] = t[c].quantile(.25)
        r[c + '_p75'] = t[c].quantile(.75)
    return r


def separar_sentido(t, u_col='u_med'):
    """Nada: el ARX no distingue subida de bajada. Para la asimetria se usa el
    signo de la deriva de u dentro de la ventana; se calcula aparte."""
    raise NotImplementedError
