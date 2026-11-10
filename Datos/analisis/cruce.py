"""Cruce completo: oxigeno, potencia de sopladores, consigna y los tres caudales.

Driver del analisis del 2026-09-01. Construye una tabla maestra en cache y
responde, en este orden:

  A  inventario y etiquetado de los caudales de cada modulo
  B  relaciones entre caudales (entrada, recirculacion, salida)
  C  oxigeno disuelto  <->  caudales
  D  oxigeno disuelto  <->  potencia de los sopladores   (ganancia y tau)
  E  consigna de OD  <->  oxigeno  <->  potencia          (lazo cerrado)
  F  consolidado en unidades de la senal de control 0-100 %

    ~/Environment/Control/bin/python cruce.py [A B C D E F]
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datos
import hidraulica as H
import identificacion as ID

warnings.filterwarnings('ignore')
AQUI = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(AQUI, 'maestra.pkl')
pd.set_option('display.width', 200)
pd.set_option('display.max_columns', 40)

# Potencia consumida por la aireacion a plena carga: percentil 99 del registro con el soplador
# encendido, no el maximo (con el segundo soplador la potencia llega a 115-124 kW).
# OJO: es potencia electrica, no la consigna del PLC.
PMAX = {'M2': 106.3, 'M3': 110.1}
MODS = ('M1', 'M2', 'M3')


# --------------------------------------------------------------------- datos
def maestra(rehacer=False):
    """1 min: OD, sensores, consigna y potencia de los 3 modulos. Cacheada."""
    if os.path.exists(CACHE) and not rehacer:
        return pd.read_pickle(CACHE)
    d = datos.oxigeno_vivo().join(datos.sopladores(), how='outer')
    d.to_pickle(CACHE)
    return d


def horas():
    return datos.horarios()


def regimen():
    r = pd.read_csv(os.path.join(AQUI, 'regimenes_diarios.csv'))
    r['dia'] = pd.to_datetime(r.dia)
    return r


def dias_de(reg, mod, *cuales):
    s = reg[(reg.modulo == mod) & (reg.regimen.isin(cuales))].dia
    return set(s.dt.date)


def filtrar_dias(s, dias):
    return s[pd.Series(s.index.date, index=s.index).isin(dias).to_numpy()]


def pct(mod, p):
    """Potencia en % de plena carga del tablero."""
    return 100 * p / PMAX[mod]


# ------------------------------------------------- A. inventario de caudales
def A_inventario(h):
    print('\n' + '=' * 78)
    print('A. INVENTARIO DE CAUDALES  --  que mide cada tag y cual sirve')
    print('=' * 78)
    d = H.diagnostico(h)
    print(d.drop(columns=['tag']).to_string(index=False, float_format='%.2f'))
    print("""
Lectura:
  Q_des  desarenador -> modulo   (se reparte en directo + UASB)
  Q_rec  tanque de lodos -> tanque de aireacion (recirculacion)
  salida CAUDALIMETRO_SALIDA: efluente de la PTAR COMPLETA, no de un modulo""")
    e = datos.leer('10')
    muertos = [c for c in e.columns
               if pd.to_numeric(e[c], errors='coerce').abs().max() < 0.5]
    print('\nTags de caudal identicamente nulos en todo el registro (%d):' % len(muertos))
    print('  ' + ', '.join(muertos))
    print('  -> no hay medida de afluente por modulo ni de bypass. El unico')
    print('     caudal de entrada a la PTAR utilizable es CAUDALIMETRO_SALIDA')
    print('     (efluente), que a volumen constante equivale al afluente total.')
    return d


# ------------------------------------------- B. relaciones entre los caudales
def B_caudales(h):
    print('\n' + '=' * 78)
    print('B. RELACIONES ENTRE CAUDALES  --  entrada, recirculacion y salida')
    print('=' * 78)
    qsal = H.salida_planta(h)
    res = {}
    for mod in ('M2', 'M3'):
        q = H.series(h, mod)
        res[mod] = q
        print('\n--- %s ---' % mod)
        j = pd.concat([q[['Q_des', 'Q_rec', 'Q_in', 'R_rec']],
                       qsal.rename('Q_ptar')], axis=1)
        print(j.describe(percentiles=[.05, .5, .95]).T.to_string(float_format='%.2f'))
        v = j.dropna(subset=['Q_des'])
        print('\n  correlacion (horario, mismas horas):')
        print(j.corr().round(3).to_string())
        # razon de recirculacion
        rr = q.R_rec.dropna()
        if len(rr) > 100:
            print('\n  razon de recirculacion Q_rec/Q_des: mediana %.2f  [p25 %.2f, p75 %.2f]  n=%d'
                  % (rr.median(), rr.quantile(.25), rr.quantile(.75), len(rr)))
        # fraccion del efluente de la PTAR que pasa por este modulo
        f = (q.Q_des / qsal).dropna()
        if len(f) > 100:
            print('  Q_des / efluente PTAR:               mediana %.2f  (3 modulos ~ 1,00 si cierra)'
                  % f.median())
        # perfil diario
        per = j.groupby(j.index.hour).median()
        print('\n  perfil diario (mediana por hora, L/s):')
        print(per[['Q_des', 'Q_rec', 'Q_ptar']].round(1).T.to_string())
    # coherencia entre modulos
    print('\n--- coherencia entre modulos ---')
    j = pd.concat([res['M2'].Q_des.rename('M2_des'), res['M3'].Q_des.rename('M3_des'),
                   res['M2'].Q_rec.rename('M2_rec'), qsal.rename('Q_ptar')], axis=1)
    print(j.corr().round(3).to_string())
    per = j.groupby(j.index.hour).median()
    print('\n  suma de los dos desarenadores medidos vs efluente PTAR:')
    s = (per.M2_des + per.M3_des)
    print('   mediana suma %.1f L/s  |  mediana efluente %.1f L/s  |  razon %.2f'
          % (s.median(), per.Q_ptar.median(), s.median() / per.Q_ptar.median()))
    return res, qsal


# ------------------------------------------------ C. oxigeno frente a caudal
def C_od_caudal(d, h):
    print('\n' + '=' * 78)
    print('C. OXIGENO DISUELTO  <->  CAUDALES')
    print('=' * 78)
    print("""
Advertencia de metodo. El registro horario de caudal NO es un promedio de la
hora: es una muestra instantanea. Se comprueba con la razon sigma(diff)/sigma
entre muestras consecutivas, que vale 0,57 a 1,11 (una serie sin memoria da
1,41; una serie suave da mucho menos que 1). Por eso la correlacion hora a hora
es casi cero aunque la relacion fisica exista: hay que agregar antes de
correlacionar.""")
    qsal = H.salida_planta(h)
    oh = d.resample('1h').mean()
    for mod in ('M2', 'M3'):
        q = H.series(h, mod)
        print('\n--- %s ---' % mod)
        for nom, s in [('Q_des', q.Q_des), ('Q_rec', q.Q_rec), ('Q_ptar', qsal)]:
            if s.dropna().empty:
                continue
            for var, y in [('OD', oh[mod + '_od']), ('potencia', oh[mod + '_pot'])]:
                t = H.corr_por_agregacion(s, y, retardos=range(0, 7))
                if len(t) == 0:
                    continue
                b = t.iloc[t.r_perfil.abs().to_numpy().argmax()]
                print('  %-7s -> %-8s  mejor retardo %d h:  r_hora %+.2f | r_dia %+.2f | r_perfil %+.2f  (n=%d)'
                      % (nom, var, b.retardo_h, b.r_hora, b.r_dia, b.r_perfil, b.n))
    print("""
Lectura: la relacion caudal->oxigeno solo aparece sobre el perfil de 24 h y con
retardo de horas. Es la firma de una perturbacion de carga que viaja con el
agua, no de un acople hidraulico rapido.""")


# ---------------------------------- D. identificacion: ganancia y constante de tiempo
def D_identificacion(d, reg, h=None):
    print('\n' + '=' * 78)
    print('D. GANANCIA Y CONSTANTE DE TIEMPO  --  regresion ARX sobre 1 min')
    print('=' * 78)
    print("""
Modelo:  y[k+1] = phi*y[k] + gamma*u[k] + delta   ->   tau = -Ts/ln(phi),
K = gamma/(1-phi), es decir  dy/dt = (K*u - y)/tau.  u = potencia del tablero
en % de plena carga (M2 106,3 kW, M3 110,1 kW). Cada ventana se valida
simulando en lazo abierto desde y[0]: se exige R2 de SIMULACION > 0,5.""")
    res = {}
    for mod in ('M2', 'M3'):
        y = d[mod + '_od']; u = pct(mod, d[mod + '_pot'])
        for etiqueta, cuales in [('lazo abierto (manual)', ('manual', 'manual_maximo', 'manual_fijo')),
                                 ('lazo cerrado (PID)', ('pid',))]:
            dias = dias_de(reg, mod, *cuales)
            yy, uu = filtrar_dias(y, dias), filtrar_dias(u, dias)
            t = ID.barrido(yy, uu, ventana=180, paso=60)
            res[(mod, etiqueta)] = t
            if len(t) == 0:
                print('\n%s  %s: sin ventanas validas' % (mod, etiqueta)); continue
            # asimetria: signo de la deriva de u dentro de la ventana
            print('\n%s  %s   ventanas validas: %d  (dias %d)'
                  % (mod, etiqueta, len(t), len(dias)))
            print('   tau  [min]  mediana %6.1f   IQR %6.1f - %6.1f' %
                  (t.tau.median(), t.tau.quantile(.25), t.tau.quantile(.75)))
            print('   K [mg/L por %% de plena carga]  mediana %7.4f   IQR %7.4f - %7.4f' %
                  (t.K.median(), t.K.quantile(.25), t.K.quantile(.75)))
            b0 = t.K / (t.tau / 60)
            print('   b0 = K/tau [mg/L/(%%·h)]        mediana %7.4f   IQR %7.4f - %7.4f' %
                  (b0.median(), b0.quantile(.25), b0.quantile(.75)))
            print('   R2 de simulacion               mediana %6.3f' % t.r2_sim.median())
            print('   K positiva en %.0f %% de las ventanas' % (100 * (t.K > 0).mean()))
    return res


def D2_estructura(d, reg, h):
    """Como cambian K y tau con el punto de operacion, el sentido y el caudal."""
    print('\n' + '-' * 78)
    print('D.2  De que depende la ganancia')
    print('-' * 78)
    qsal = H.salida_planta(h)
    for mod in ('M2', 'M3'):
        y = d[mod + '_od']; u = pct(mod, d[mod + '_pot'])
        dias = dias_de(reg, mod, 'manual', 'manual_maximo', 'manual_fijo')
        yy, uu = filtrar_dias(y, dias), filtrar_dias(u, dias)
        t = ID.barrido(yy, uu, ventana=180, paso=60)
        if len(t) < 50:
            continue
        print('\n--- %s (lazo abierto, n=%d ventanas) ---' % (mod, len(t)))
        # sentido: signo de la deriva de u dentro de la ventana
        for col, etiqueta, cortes in [
                ('y_med', 'nivel de OD [mg/L]', [0, .5, 1.5, 3, 20]),
                ('u_med', 'nivel de potencia [% plena carga]', [0, 20, 40, 60, 101])]:
            g = t.groupby(pd.cut(t[col], cortes), observed=True)
            r = g.agg(n=('K', 'size'), tau=('tau', 'median'), K=('K', 'median'))
            r['b0'] = r.K / (r.tau / 60)
            print('\n  por %s:' % etiqueta)
            print(r.to_string(float_format='%.4f'))
        # asimetria subida / bajada
        print('\n  asimetria por sentido de la excitacion:')
        for nom, sel in [('u sube', t.K.notna())]:
            pass
        print('    (se calcula aparte, con escalones; el ARX promedia los dos sentidos)')
    # con el caudal como regresor adicional, a resolucion horaria
    print('\n' + '-' * 78)
    print('D.3  El caudal como entrada adicional:  dy/dt = (K*u - y)/tau + c_Q*Q')
    print('-' * 78)
    oh = d.resample('1h').mean()
    for mod in ('M2', 'M3'):
        q = H.series(h, mod)
        for nom, Q in [('Q_des', q.Q_des), ('Q_ptar', qsal)]:
            if Q.dropna().empty:
                continue
            base = pd.DataFrame({'y': oh[mod + '_od'], 'u': pct(mod, oh[mod + '_pot'])})
            ex = pd.DataFrame({'Q': Q.reindex(base.index)}).ffill(limit=1)
            a = ID.barrido(base.y, base.u, ventana=48, paso=24, ts_min=60.0,
                           std_u_min=3.0, rango_y_min=0.3, r2_min=0.3,
                           tau_lim=(2., 600.))
            b = ID.barrido(base.y, base.u, extra=ex, ventana=48, paso=24, ts_min=60.0,
                           std_u_min=3.0, rango_y_min=0.3, r2_min=0.3,
                           tau_lim=(2., 600.))
            if len(b) < 20:
                continue
            cq = np.array([c[0] for c in b.coef_extra])
            print('  %s %-7s  n=%3d  R2 sin Q %.3f -> con Q %.3f   coef_Q mediana %+.5f mg/L por (L/s·h)'
                  % (mod, nom, len(b), a.r2_sim.median() if len(a) else np.nan,
                     b.r2_sim.median(), np.median(cq) * 60))


# ------------------------------- E. consigna <-> oxigeno <-> potencia (lazo cerrado)
def E_lazo(d, reg):
    print('\n' + '=' * 78)
    print('E. CONSIGNA  <->  OXIGENO  <->  POTENCIA   (el lazo tal como opera)')
    print('=' * 78)
    for mod in MODS:
        sp = d[mod + '_sp']; y = d[mod + '_od']
        pot = d.get(mod + '_pot')
        dias = dias_de(reg, mod, 'pid')
        s = filtrar_dias(sp, dias); yy = filtrar_dias(y, dias)
        j = pd.concat([s.rename('r'), yy.rename('y')], axis=1).dropna()
        if len(j) < 1000:
            print('\n%s: sin dias de PID suficientes' % mod); continue
        e = j.y - j.r
        print('\n--- %s   (%d dias de PID, %d min) ---' % (mod, len(dias), len(j)))
        print('   consigna: mediana %.2f mg/L   valores distintos %d   cambios %d'
              % (j.r.median(), j.r.nunique(), (j.r.diff().abs() > .02).sum()))
        print('   error y-r: media %+.3f   IAE %.3f   RMS %.3f   dentro de +-0,2: %.1f %%'
              % (e.mean(), e.abs().mean(), np.sqrt((e ** 2).mean()), 100 * (e.abs() < .2).mean()))
        if pot is not None:
            pp = filtrar_dias(pct(mod, pot), dias)
            k = pd.concat([j, pp.rename('u')], axis=1).dropna()
            if len(k) > 1000:
                ee = k.y - k.r
                print('   potencia: media %.1f %% de plena carga  |  apagado %.1f %%  |  saturado %.1f %%'
                      % (k.u.mean(), 100 * (k.u < 2).mean(), 100 * (k.u > 95).mean()))
                print('   corr(error, potencia) = %+.3f   corr(error, dPot) = %+.3f'
                      % (ee.corr(k.u), ee.corr(k.u.diff())))
                # respuesta a cambios de consigna
                ch = k.r.diff().abs() > .02
                print('   cambios de consigna dentro de dias de PID: %d' % ch.sum())


# ------------------------------------------------------ tablas para las figuras
def tabla_arx(d, reg, h, rehacer=False):
    """Una fila por ventana ARX de 3 h, con el punto de operacion, la
    perturbacion implicita y el caudal mas cercano. Se cachea en CSV."""
    p = os.path.join(AQUI, 'arx_ventanas.csv')
    if os.path.exists(p) and not rehacer:
        t = pd.read_csv(p, parse_dates=['inicio'])
        return t
    qs = H.salida_planta(h)
    out = []
    for mod in ('M2', 'M3'):
        y = d[mod + '_od']; u = pct(mod, d[mod + '_pot'])
        q = H.series(h, mod)
        for etiqueta, cuales in [('abierto', ('manual', 'manual_maximo', 'manual_fijo')),
                                 ('cerrado', ('pid',))]:
            dias = dias_de(reg, mod, *cuales)
            t = ID.barrido(filtrar_dias(y, dias), filtrar_dias(u, dias),
                           ventana=180, paso=60)
            if len(t) == 0:
                continue
            a = -np.log(t.phi)                       # 1/min
            t['modulo'] = mod; t['lazo'] = etiqueta
            t['a_h'] = a * 60                        # polo, 1/h
            t['b0'] = t.K * a * 60                   # mg/L/(%pot·h)
            t['c_h'] = t.delta * a * 60 / (1 - t.phi)
            t['f2'] = t.c_h - t.a_h * 2.0            # perturbacion total en y=2
            idx = pd.DatetimeIndex(t.inicio)
            for nom, s in [('Q_des', q.Q_des), ('Q_rec', q.Q_rec), ('Q_ptar', qs)]:
                t[nom] = s.reindex(idx, method='nearest',
                                   tolerance=pd.Timedelta('90min')).to_numpy()
            out.append(t)
    T = pd.concat(out, ignore_index=True)
    T['hora'] = T.inicio.dt.hour
    T.drop(columns=[c for c in ('coef_extra',) if c in T]).to_csv(p, index=False)
    print('  arx_ventanas.csv:', len(T), 'ventanas')
    return T


# -------------------------------------------- F. consolidado en unidades de control
# Pendiente de la curva estatica del actuador: puntos de potencia por punto de
# consigna, de ANALISIS_ACTUADOR_2026-08-30.md 4.4 (tramo 1 / tramo 2).
PEND = {'M2': (0.74, 1.14), 'M3': (0.68, 0.37)}
NIVELES = [(0, .5, 'limitado por demanda'), (.5, 1.5, 'bajo'),
           (1.5, 3., 'consigna (2,0 mg/L)'), (3., 20., 'alto')]


def F_consolidado(T):
    print('\n' + '=' * 78)
    print('F. CONSOLIDADO EN UNIDADES DE LA SENAL DE CONTROL (0-100 %)')
    print('=' * 78)
    print("""
La cadena:  u [0-100 %] -> 4-20 mA -> variador -> 2 sopladores -> kW -> KLa -> OD
La identificacion de arriba esta en % de plena carga ELECTRICA. Para pasarla a
consigna se multiplica por la pendiente de la curva estatica del actuador
(ANALISIS_ACTUADOR_2026-08-30.md 4.4), que es la unica parte de la cadena que
no se pudo medir directamente en el historico.""")
    ab = T[T.lazo == 'abierto']
    for mod in ('M2', 'M3'):
        s = ab[ab.modulo == mod]
        p1, p2 = PEND[mod]
        print('\n--- %s   (pendiente del actuador %.2f a %.2f %%pot/%%cmd) ---' % (mod, p1, p2))
        print('  %-22s %5s %7s %8s %9s %14s' %
              ('punto de operacion', 'n', 'tau[min]', 'K[/%pot]', 'b0[/%pot]', 'b0 [/%cmd]'))
        for lo, hi, nom in NIVELES:
            g = s[(s.y_med > lo) & (s.y_med <= hi)]
            if len(g) < 15:
                continue
            k, tau, b0 = g.K.median(), g.tau.median(), g.b0.median()
            print('  %-22s %5d %8.1f %8.4f %9.4f %6.3f - %.3f' %
                  (nom, len(g), tau, k, b0, b0 * min(p1, p2), b0 * max(p1, p2)))
    print("""
Lectura para el diseno: b0 no es un numero con incertidumbre, es una FUNCION del
punto de operacion. El factor 12 que el informe del 26 de agosto reportaba como
dispersion de la planta es, en su mayor parte, esta dependencia -- y por tanto
es predecible, no aleatoria.""")


def main(secciones=('A', 'B', 'C', 'D', 'E', 'F')):
    d = maestra(); reg = regimen(); h = horas()
    if 'A' in secciones: A_inventario(h)
    if 'B' in secciones: B_caudales(h)
    if 'C' in secciones: C_od_caudal(d, h)
    if 'D' in secciones:
        D_identificacion(d, reg); D2_estructura(d, reg, h)
    if 'E' in secciones: E_lazo(d, reg)
    T = tabla_arx(d, reg, h)
    if 'F' in secciones: F_consolidado(T)
    return d, reg, h, T


if __name__ == '__main__':
    main(sys.argv[1:] or ('A', 'B', 'C', 'D', 'E', 'F'))
