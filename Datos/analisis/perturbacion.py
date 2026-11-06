"""La perturbacion del lazo de oxigeno de Tunja, medida y generable.

En la forma que usa el ADRC,

    y' = f + b0 u

`f` agrupa TODO lo que no es la accion de control: el polo de la planta (-y/tau),
la respiracion de la biomasa, el caudal que entra, la recirculacion y la parte de
la no linealidad del actuador que la conversion kW -> % no captura.

Este modulo hace dos cosas:

  medir(mod)   -> descompone la f medida del historico en sus piezas
  generar(...) -> devuelve una f(t) sintetica con esas mismas piezas, para
                  alimentar simulaciones y sintonizar el observador

NO se usa el fichero de influente del BSM1 (`t_Si_Ss_...txt`). Ese es el
influente seco de Copenhague: su caudal oscila un 94 % sobre la media y su carga
de DQO soluble un factor 7 a lo largo del dia. Tunja oscila un 26-43 % en caudal.
Sintonizar el observador contra el BSM1 es sintonizar para otra planta.
"""
import numpy as np
import pandas as pd

import cruce
import hidraulica as H

# b0 DE DISENO, en mg/(L*h*%) de plena carga electrica. En M2 se elige 0,15: cae dentro
# del rango intercuartilico de las ventanas con OD entre 1,5 y 3 mg/L (cerca de la
# referencia; mediana 0,134). El rango de TODAS las ventanas no lo contiene porque lo
# dominan las ventanas con OD bajo. Donde no hay valor de diseno se usa la mediana medida.
B0_DISENO = {'M2': 0.15}

# Las ventanas ARX duran 3 h; cada f2 se fecha en el CENTRO de su ventana.
CENTRO = pd.Timedelta('90min')
# Periodo sano del caudalimetro de entrada: el mismo de la figura de caudales. En M2
# termina el 5-sep-2025: el 6-sep a las 10:00 la lectura se congela en 11,44 L/s.
SANA_QDES = {'M2': slice('2024-10-16', '2025-09-05'),
             'M3': slice('2024-10-16', '2025-09-30')}
# Tramos dentro del periodo sano en que el caudalimetro marca menos de 5 L/s dias
# seguidos. En mar-2025 M2 opera en manual con el soplador al 100 % y el OD en
# 0,5 mg/L: no es falta de agua, es el sensor.
FALLA_QDES = {'M2': [slice('2025-01-22', '2025-01-24'), slice('2025-02-27', '2025-05-12')]}
# Un mes cuenta para el nivel mensual si tiene al menos 50 ventanas (unos 2 dias).
MIN_VENT_MES = 50
# Ventana atipica: f2 a mas de ATIPICO desviaciones robustas de la mediana. En M2 son
# 12 de 1.225; 7 son del 4 al 8 de octubre de 2025, con f2 entre -60 y -162.
ATIPICO = 10


def serie_f(T, mod):
    """Ventanas ARX de `mod`, indexadas por el centro de la ventana."""
    tt = T[T.modulo == mod].copy()
    tt.index = pd.DatetimeIndex(tt.inicio) + CENTRO
    return tt.sort_index()


def caudal_sano(h, mod):
    """Caudal de entrada de `mod` en su periodo sano, sin los tramos de falla [L/s]."""
    q = H.series(h, mod).Q_des[SANA_QDES[mod]].copy()
    for tramo in FALLA_QDES.get(mod, []):
        q.loc[tramo] = np.nan
    return q.dropna()


def perfil_caudal(mod, h=None):
    """Perfil diario del caudal de entrada en su periodo sano [L/s]: media de
    cada hora, el mismo que muestra la figura de caudales."""
    h = cruce.horas() if h is None else h
    q = caudal_sano(h, mod)
    return q.groupby(q.index.hour).mean()


def medir(mod, T=None, h=None):
    """Descompone la f medida del historico. Devuelve un dict con las piezas.

        f2 = nivel + ciclo diario + residuo

    Antes se descartan las ventanas atipicas (ATIPICO). El nivel es la mediana de
    las f2, el ciclo diario la mediana de cada hora (centrada en cero) y el residuo
    lo que queda al quitarle a cada ventana el nivel y el ciclo de su hora: su sigma
    robusta y su correlacion a 1 h dan el termino aleatorio del generador.
    """
    if T is None:
        T = pd.read_csv('arx_ventanas.csv', parse_dates=['inicio'])
        T['b0'] = T.K / (T.tau / 60)
    h = cruce.horas() if h is None else h
    tt = serie_f(T[T.lazo == 'abierto'], mod)      # solo dias manuales, como la identificacion
    f = tt.f2.dropna()
    ab = T[(T.modulo == mod) & (T.lazo == 'abierto')]
    sp = ab[ab.y_med.between(1.5, 3)]
    rob = lambda x: float((x.quantile(.75) - x.quantile(.25)) / 1.349)
    # ventanas atipicas fuera
    z_rob = (f - f.median()) / rob(f)
    n_atipicas = int((z_rob.abs() > ATIPICO).sum())
    f = f[z_rob.abs() <= ATIPICO]

    # ciclo diario medido
    perfil_f = f.groupby(f.index.hour).median().reindex(range(24))
    ciclo = perfil_f - perfil_f.mean()
    # nivel de cada mes: solo informativo, no entra en el residuo ni en la senal
    g = f.groupby(pd.Grouper(freq='MS'))
    n_mes, mes = g.size(), g.median()
    mes_ok = mes[n_mes >= MIN_VENT_MES]
    # residuo
    resid = f - f.median() - ciclo.reindex(f.index.hour).to_numpy()
    # constante de tiempo DEL RESIDUO: correlacion entre los pares de residuos separados
    # EXACTAMENTE 1 h (en un OU, rho(1 h) = exp(-60/tau_f)). No se emparejan ventanas
    # que quedan a lados de un hueco.
    sig1 = resid.reindex(resid.index + pd.Timedelta('1h')).to_numpy()
    ok1 = ~np.isnan(sig1)
    ac = float(np.corrcoef(resid.to_numpy()[ok1], sig1[ok1])[0, 1])
    # parte del ciclo que explica el caudal: recta entre el perfil diario de f
    # (mediana de cada hora, la misma del ciclo) y el perfil diario MEDIDO del caudal
    # de entrada (el de la figura de caudales); su pendiente por el vaiven de ese perfil
    pQ = perfil_caudal(mod, h)
    pf = perfil_f.reindex(pQ.index)
    a = np.polyfit(pQ.to_numpy(), pf.to_numpy(), 1)[0]
    r_fQ = float(np.corrcoef(pQ.to_numpy(), pf.to_numpy())[0, 1])
    return dict(
        mod=mod, n=len(f), n_atipicas=n_atipicas, b0=B0_DISENO.get(mod, float(sp.b0.median())),
        b0_medido=float(sp.b0.median()), b0_q25=float(sp.b0.quantile(.25)),
        b0_q75=float(sp.b0.quantile(.75)), tau_consigna_h=float(sp.tau.median() / 60),
        f0=float(f.median()),
        ciclo=ciclo, amp_ciclo=float(perfil_f.max() - perfil_f.min()),
        dfdQ=float(a), corr_fQ=r_fQ, vaiven_Q=float(pQ.max() - pQ.min()),
        amp_caudal=float(abs(a) * (pQ.max() - pQ.min())),
        nivel_mes=mes_ok, n_mes=n_mes,
        f_mes_min=float(mes_ok.min()), f_mes_max=float(mes_ok.max()),
        cambio_mes=float(mes_ok.max() - mes_ok.min()),
        sigma_f=rob(f), sigma_res=rob(resid),
        rho_1h=ac, n_pares_1h=int(ok1.sum()),
        tau_f_min=float(-60 / np.log(ac)) if 0 < ac < 1 else np.nan,
    )


_PIEZAS = {}


def generar(mod, dias=14, dt_min=1.0, semilla=0, f0=None, z=None, con_residuo=True):
    """f(t) sintetica con las piezas medidas de `mod`:

        f(t) = f0 + c(t) + xi(t)

    c(t) es el ciclo diario medido (mediana de cada hora), repetido cada dia, y
    xi un Ornstein-Uhlenbeck con la sigma del residuo y la constante de tiempo
    medidas, con su discretizacion EXACTA (Gillespie, 1996):
        xi[k+1] = a xi[k] + w[k],  a = exp(-dt/tau_f),  w ~ N(0, sigma^2 (1 - a^2)),
    de modo que su desviacion estacionaria es sigma y su autocorrelacion
    exp(-t/tau_f), sin error de integracion. El cambio de nivel entre meses NO
    entra en la senal: se simula como escenarios, pasando `f0` = nivel del mes
    mas bajo o del mas alto.

    `z` son las piezas de medir(); si no se pasan, se miden una vez y se guardan.
    Devuelve una Serie indexada en horas desde 0.
    """
    if z is None:
        if mod not in _PIEZAS:
            _PIEZAS[mod] = medir(mod)
        z = _PIEZAS[mod]
    rng = np.random.default_rng(semilla)
    n = int(dias * 24 * 60 / dt_min)
    t_h = np.arange(n) * dt_min / 60.0

    nivel = z['f0'] if f0 is None else f0
    # cada valor del ciclo representa el centro de su hora
    c = np.interp(t_h % 24, np.arange(24) + 0.5, z['ciclo'].to_numpy(), period=24)
    f = nivel + c
    if con_residuo:
        xi = np.empty(n); xi[0] = 0.0
        a = np.exp(-dt_min / z['tau_f_min'])
        s = z['sigma_res'] * np.sqrt(1 - a**2)
        for k in range(n - 1):
            xi[k + 1] = a * xi[k] + rng.normal(0, s)
        f += xi
    return pd.Series(f, index=pd.Index(t_h, name='h'), name='f')


# --- sintonia del observador -----------------------------------------------
def error_por_perturbacion(df_dt, omega_o, omega_c):
    """Error de OD en regimen que deja un ESO de 2.o orden ante una f que
    cambia a ritmo `df_dt` [mg/(L.h) por hora].

    ESO: beta1 = 2*wo, beta2 = wo^2.  La transferencia de f a (f - z2) es
    s(s+2wo)/(s+wo)^2; ante una rampa de pendiente df_dt el error de estimacion
    en regimen es 2*df_dt/wo, y el lazo lo traduce en un error de OD de
    e_f/omega_c.
    """
    return 2.0 * df_dt / (omega_o * omega_c)


def omega_o_minima(df_dt, omega_c, e_objetivo):
    """wo minima para que la perturbacion no deje mas de `e_objetivo` mg/L."""
    return 2.0 * df_dt / (omega_c * e_objetivo)
