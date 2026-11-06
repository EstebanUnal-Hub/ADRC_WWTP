"""La cadena de actuacion: de la senal de control del PLC a la potencia medida.

El historiador NO guarda la senal de control. Lo que hay es potencia electrica
del tablero de aireacion. Este modulo reconstruye lo que se puede reconstruir de
la senal de 0 a 100 % que el PLC manda a los variadores, y deja explicito lo que
no.

Cadena documentada en los informes de servicio (carpeta Informes/):

    PID  u in [0,100] %                                    <- lo que falta
      |  reparto 50/50 (informe 2024-11-27, ratificado 2025-06-06)
      +--> soplador 1:  c1 = min(2u, 100)
      +--> soplador 2:  c2 = max(0, 2u - 100)
      |
      |  salida analogica 4-20 mA del PLC   (0 % = 4 mA, 100 % = 20 mA)
      |  recta de linealizacion del variador, parametros P0133 / P0134
      |  banda muerta: por debajo de ~20 Hz el variador no opera; el PLC ademas
      |  mantiene el motor apagado mientras c < 30 % (informe 2024-11-27)
      v
    frecuencia -> velocidad -> caudal de aire -> OD                 y = OD [mg/L]
      |
      +--> potencia activa del tablero  P [kW]              <- lo unico registrado

Consecuencias de que el medidor este del lado de RED del variador:
  - VOLTAJE_L12 se queda en 473-500 V y FRECUENCIA en 60,00 Hz pase lo que pase:
    son la tension y la frecuencia de la acometida, no las del motor. El tag
    `M?_FRECUENCIA[i]` no contiene informacion de velocidad.
  - THD_CORRIENTE ~ 27 % es la firma del rectificador de 6 pulsos del variador,
    que es como se comprueba de que lado esta el medidor.
"""
import numpy as np
import pandas as pd

# Canal de potencia del tablero de aireacion de cada modulo.
# M1 no tiene medidor: solo tiene OD y consigna.
MEDIDOR = {'M2': 'M2_pot', 'M3': 'M3_pot'}

# Parametros de la cadena, tomados de los informes de servicio.
REPARTO = 50.0    # % de la senal del PID en que entra el segundo soplador
C_MIN = 30.0      # % de consigna de cada soplador por debajo del cual no arranca


def u_arranque(soplador=1):
    """Consigna del PID a la que arranca cada soplador, con el reparto 50/50."""
    return C_MIN / 2 if soplador == 1 else REPARTO + C_MIN / 2


# --------------------------------------------------------------------------
# Mesetas: los niveles en que se estaciona la potencia
# --------------------------------------------------------------------------

def mesetas(s, tol=1.5, min_len=30):
    """Tramos donde P se mantiene dentro de +-tol kW durante >= min_len minutos.

    En operacion manual el operario teclea una consigna y la deja: cada meseta
    es un nivel de consigna distinto. El histograma de mesetas es, por tanto, el
    espectro de consignas que la planta ha usado realmente.
    """
    s = s.dropna()
    s = s[~s.index.duplicated()]
    v = s.to_numpy(float)
    t = s.index
    hueco = np.diff(t.values).astype('timedelta64[s]').astype(float)
    out, i = [], 0
    while i < len(v):
        j, lo, hi = i + 1, v[i], v[i]
        while j < len(v) and hueco[j - 1] <= 90:
            lo, hi = min(lo, v[j]), max(hi, v[j])
            if hi - lo > 2 * tol:
                break
            j += 1
        if j - i >= min_len:
            out.append((t[i], t[j - 1], j - i, float(np.median(v[i:j]))))
            i = j
        else:
            i += 1
    return pd.DataFrame(out, columns=['ini', 'fin', 'min', 'P'])


# --------------------------------------------------------------------------
# Cuantas maquinas cuelgan de un mismo medidor
# --------------------------------------------------------------------------

def saltos(s, min_kw=6.0):
    """Saltos de potencia de un minuto al siguiente, con las dos maquinas encendidas.

    Si de un medidor cuelgan dos sopladores, al arrancar o parar el segundo la
    potencia salta un escalon repetible. La moda de P_despues/P_antes dice si las
    dos maquinas van a la misma consigna (razon 2) o a consignas distintas.
    """
    s = s.dropna()
    s = s[~s.index.duplicated()]
    dt = s.index.to_series().diff().dt.total_seconds()
    a, b = s.shift(1), s
    m = (dt <= 90) & (a > 5) & (b > 5) & ((b - a).abs() > min_kw)
    return pd.DataFrame({'antes': a[m], 'despues': b[m], 'razon': (b / a)[m]})


def firma_dos_maquinas(s, ancho=0.05):
    """Moda de la razon de salto y el par (P_antes, P_despues) que la produce."""
    j = saltos(s)
    r = j.razon[(j.razon > 1.05) & (j.razon < 3.0)]
    if len(r) < 50:
        return None
    bins = np.arange(1.0, 3.0 + ancho, ancho)
    h, _ = np.histogram(r, bins=bins)
    k = int(np.argmax(h))
    lo, hi = bins[k], bins[k + 1]
    sel = j[(j.razon >= lo) & (j.razon <= hi)]
    return dict(razon=(lo + hi) / 2, n=len(sel), frac=len(sel) / len(j),
                antes=float(sel.antes.median()), despues=float(sel.despues.median()),
                salto=float((sel.despues - sel.antes).median()))


# --------------------------------------------------------------------------
# Los quiebres de la curva estatica, leidos del histograma de potencia
# --------------------------------------------------------------------------

def _piso_techo(P):
    """Nivel mas bajo y mas alto que la planta SOSTIENE, ponderando por duracion.

    Sobre las mesetas y no sobre las muestras sueltas: las muestras sueltas
    incluyen los transitorios de arranque y parada, que no son niveles de
    operacion y ensucian los percentiles extremos.
    """
    m = mesetas(P)
    m = m[m.P > 3]
    if len(m) < 50:
        return np.nan, np.nan
    w = np.repeat(m.P.to_numpy(), np.maximum(1, m['min'].to_numpy() // 10))
    return float(np.percentile(w, 1)), float(np.percentile(w, 99))


def quiebres(P, P_mesetas=None, dens_min=0.45):
    """Piso, techo y banda prohibida de la potencia, en kW.

    Con el reparto 50/50 y la banda muerta del variador, al cruzar u = 65 % el
    segundo soplador pasa de apagado a su minimo de golpe. Entre la potencia con
    un soplador al maximo y esa misma potencia mas el minimo del segundo hay un
    intervalo que la planta no puede sostener: la banda prohibida. Aparece en el
    histograma como una depresion, y la prediccion falsable es que su ancho debe
    coincidir con el piso, porque el escalon que la abre es un soplador
    arrancando en su minimo.
    """
    on = P.dropna()
    on = on[on > 3]
    if len(on) < 2000:
        return None
    piso, techo = _piso_techo(P if P_mesetas is None else P_mesetas)
    if not np.isfinite(piso):
        return None
    paso = 2.0
    bins = np.arange(0, techo + paso, paso)
    h, e = np.histogram(on, bins=bins, density=True)
    centro = 0.5 * (e[:-1] + e[1:])
    util = (centro > piso * 1.3) & (centro < techo * 0.95)
    ref = 1.0 / (techo - 3)                    # densidad de una uniforme sobre el rango
    # depresion mas ancha y profunda: subarreglo de suma maxima de (umbral - h)
    d = np.where(util, dens_min * ref - h, -np.inf)
    mejor = (0.0, -1, -1)
    acc, ini = 0.0, 0
    for i, v in enumerate(d):
        if acc <= 0:
            acc, ini = v, i
        else:
            acc += v
        if acc > mejor[0]:
            mejor = (acc, ini, i)
    if mejor[1] < 0:
        return dict(piso=piso, techo=techo, p1max=np.nan, p2min=np.nan,
                    banda_ancho=np.nan, frac_banda=np.nan, dens_dentro=np.nan,
                    dens_fuera=np.nan)
    p1max, p2min = float(e[mejor[1]]), float(e[mejor[2] + 1])
    dentro = (on >= p1max) & (on < p2min)
    frac = float(dentro.mean())
    return dict(piso=piso, techo=techo, p1max=p1max, p2min=p2min,
                banda_ancho=p2min - p1max, frac_banda=frac,
                dens_dentro=frac / (p2min - p1max),
                dens_fuera=(1 - frac) / (techo - 3 - (p2min - p1max)))


# --------------------------------------------------------------------------
# El mapa u -> P y su inversa
# --------------------------------------------------------------------------

class Cadena:
    """Mapa estatico entre la consigna del PID (%) y la potencia del tablero (kW).

    Cuatro numeros, todos medidos: piso (un soplador al minimo del variador),
    p1max (un soplador al maximo), p2min (piso + el segundo arrancando) y techo
    (los dos al maximo). La geometria entre ellos la fija el reparto 50/50 y la
    banda muerta, que estan documentados.
    """

    def __init__(self, piso, p1max, p2min, techo):
        self.piso, self.p1max, self.p2min, self.techo = piso, p1max, p2min, techo
        self.u1 = u_arranque(1)                 # 15 %: arranca el soplador 1
        self.u2 = u_arranque(2)                 # 65 %: arranca el soplador 2

    def P(self, u):
        """Potencia que corresponde a una consigna del PID."""
        u = np.asarray(u, float)
        out = np.zeros_like(u)
        a = (u >= self.u1) & (u <= REPARTO)
        out[a] = self.piso + (self.p1max - self.piso) * (2 * u[a] - C_MIN) / (100 - C_MIN)
        b = (u > REPARTO) & (u < self.u2)       # el segundo aun no arranca
        out[b] = self.p1max
        c = u >= self.u2
        out[c] = self.p2min + (self.techo - self.p2min) * (2 * u[c] - 100 - C_MIN) / (100 - C_MIN)
        return out

    def u(self, P):
        """Consigna que explica una potencia. NaN donde el mapa no es invertible.

        Dentro de la banda prohibida cualquier u entre 50 y 65 % da la misma
        potencia: ahi la senal de control no se puede recuperar, y el resultado
        es NaN a proposito.
        """
        P = np.asarray(P, float)
        out = np.full(P.shape, np.nan)
        out[P < 3] = 0.0
        a = (P >= 3) & (P <= self.p1max)
        out[a] = (C_MIN + (100 - C_MIN) * (P[a] - self.piso) / (self.p1max - self.piso)) / 2
        c = P >= self.p2min
        out[c] = (100 + C_MIN + (100 - C_MIN) * (P[c] - self.p2min) / (self.techo - self.p2min)) / 2
        return np.clip(out, 0, 100)

    def pendientes(self):
        """dP/du en cada tramo, en kW por punto de consigna y en % de plena carga."""
        s1 = (self.p1max - self.piso) / (REPARTO - self.u1)
        s2 = (self.techo - self.p2min) / (100 - self.u2)
        return dict(kW_por_pct_tramo1=s1, kW_por_pct_tramo2=s2,
                    pct_pot_por_pct_cmd_1=100 * s1 / self.techo,
                    pct_pot_por_pct_cmd_2=100 * s2 / self.techo,
                    salto_arranque_1=100 * self.piso / self.techo,
                    salto_arranque_2=100 * (self.p2min - self.p1max) / self.techo)


# --------------------------------------------------------------------------
# Accion integral: comprobar que el lazo estaba cerrado de verdad
# --------------------------------------------------------------------------

def accion_integral(d, reg, mod, regimen, n_boot=400, semilla=1):
    """Regresa dP/dt sobre (e, de/dt). Con un PI, dP/dt = g'(Kp*de/dt + Ki*e).

    El coeficiente de e mide la accion integral. La realimentacion de la planta
    haria el efecto contrario (mas potencia -> mas OD -> menos error), asi que un
    coeficiente positivo solo lo puede producir el controlador.
    """
    dias = set(pd.to_datetime(reg[(reg.modulo == mod) & (reg.regimen == regimen)].dia).dt.date)
    g = pd.DataFrame({'od': d[mod + '_od'], 'sp': d[mod + '_sp'],
                      'P': d[MEDIDOR[mod]]}).dropna()
    g = g[pd.Series(g.index.date, index=g.index).isin(dias)]
    if len(g) < 2000:
        return None
    dt = g.index.to_series().diff().dt.total_seconds()
    g['e'] = g.sp - g.od
    g['dP'] = g.P.diff().where(dt <= 90)
    g['de'] = g.e.diff().where(dt <= 90)
    g = g.dropna(subset=['dP', 'de'])
    g = g[(g.P > 5) & (g.P.shift(1) > 5)]        # solo con el soplador encendido
    if len(g) < 2000:
        return None
    dia = g.index.date
    X = np.c_[g.e, g.de, np.ones(len(g))]
    y = g.dP.to_numpy()
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    rng = np.random.default_rng(semilla)
    ds = np.array(sorted(set(dia)))
    filas = {v: np.flatnonzero(dia == v) for v in ds}
    B = []
    for _ in range(n_boot):                       # bootstrap por dia, no por muestra
        sel = np.concatenate([filas[v] for v in rng.choice(ds, len(ds))])
        B.append(np.linalg.lstsq(X[sel], y[sel], rcond=None)[0])
    B = np.array(B)
    return dict(n=len(g), dias=len(ds), a_e=b[0], b_de=b[1],
                a_lo=np.percentile(B[:, 0], 2.5), a_hi=np.percentile(B[:, 0], 97.5),
                Tn=b[1] / b[0] if b[0] > 0 else np.nan)


# --------------------------------------------------------------------------
# Informe
# --------------------------------------------------------------------------

def informe(d, reg):
    """Todo lo anterior sobre M2 y M3. Devuelve un dict listo para las figuras."""
    A = {}
    for mod in ('M2', 'M3'):
        P = d[MEDIDOR[mod]]
        dias = set(pd.to_datetime(reg[(reg.modulo == mod) & (reg.regimen == 'pid')].dia).dt.date)
        Ppid = P[pd.Series(P.index.date, index=P.index).isin(dias)]
        q = quiebres(Ppid, P)
        cad = Cadena(q['piso'], q['p1max'], q['p2min'], q['techo'])
        A[mod] = dict(
            mesetas=mesetas(P),
            firma=firma_dos_maquinas(P),
            quiebres=q,
            cadena=cad,
            pendientes=cad.pendientes(),
            integral_pid=accion_integral(d, reg, mod, 'pid'),
            integral_manual=accion_integral(d, reg, mod, 'manual'),
            P_pid=Ppid,
        )
        print('== %s' % mod)
        print('   piso %.1f kW | 1 soplador al maximo %.1f | reentrada %.1f | techo %.1f'
              % (q['piso'], q['p1max'], q['p2min'], q['techo']))
        print('   banda prohibida %.0f-%.0f kW (ancho %.1f, piso %.1f): %.1f %% del tiempo'
              % (q['p1max'], q['p2min'], q['banda_ancho'], q['piso'], 100 * q['frac_banda']))
        f = A[mod]['firma']
        if f:
            print('   firma de dos maquinas: razon %.2f en %d saltos, %.0f -> %.0f kW (+%.0f)'
                  % (f['razon'], f['n'], f['antes'], f['despues'], f['salto']))
        p = A[mod]['pendientes']
        print('   dP/du: %.2f y %.2f kW por punto de consigna  (%.2f y %.2f %% de plena carga)'
              % (p['kW_por_pct_tramo1'], p['kW_por_pct_tramo2'],
                 p['pct_pot_por_pct_cmd_1'], p['pct_pot_por_pct_cmd_2']))
        for k in ('integral_pid', 'integral_manual'):
            r = A[mod][k]
            if r:
                print('   %-16s a(e) = %+.3f  IC95 [%+.3f, %+.3f]  n=%d  dias=%d'
                      % (k, r['a_e'], r['a_lo'], r['a_hi'], r['n'], r['dias']))
    return A
