"""Exporta la perturbacion f(t) sintetica del lazo de oxigeno, para usarla en el ADRC.

Genera, con perturbacion.generar(), 14 dias de f a 1 min (semilla 0) para M2 y M3,
y guarda las piezas medidas (perturbacion.medir()) en f_parametros.csv.

UNIDADES  -- esto es lo que hay que mirar antes de usarlas en otra parte:

    f    [mg/(L*h)]        <- POR HORA, no por segundo ni por minuto
    b0   [mg/L/(%*h)]      <- por hora tambien
    tau  [h]               en la consigna: M2 0,31 h  ·  M3 0,429 h
    indice de tiempo: horas desde 0

Para llevarlas al ADRC_PTAR, que trabaja en SEGUNDOS:
    f_[mg/(L*s)]  = f_[mg/(L*h)]  / 3600
    b0_[mg/L/%/s] = b0_[mg/L/%/h] / 3600
"""
import os, sys, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import numpy as np, pandas as pd
import cruce, perturbacion as PT

SAL = os.path.dirname(os.path.abspath(__file__))

print('cargando el historico...')
h   = cruce.horas()
T   = pd.read_csv('arx_ventanas.csv', parse_dates=['inicio'])
T['b0'] = T.K / (T.tau / 60)
print('  ventanas ARX: %s' % f'{len(T):,}')

# ------------------------------------------------------------- f GENERADA
for mod in ('M2', 'M3'):
    g = PT.generar(mod, dias=14, dt_min=1.0, semilla=0)
    G = pd.DataFrame({'h': g.index.to_numpy(), 'f': g.to_numpy()})
    p = os.path.join(SAL, f'f_generada_{mod}_14d_1min.csv')
    G.to_csv(p, index=False, float_format='%.5f')
    print('  %-24s %7d filas  f: media %+.2f, sigma %.2f  [mg/(L*h)], indice en HORAS'
          % (os.path.basename(p), len(G), G.f.mean(), G.f.std()))

# ------------------------------------------------------------- parametros
PZ = {m: PT.medir(m, T=T, h=h) for m in ('M2', 'M3')}
par = pd.DataFrame({m: {k: v for k, v in PZ[m].items()
                        if isinstance(v, (int, float, np.floating))} for m in ('M2', 'M3')})
par.to_csv(os.path.join(SAL, 'f_parametros.csv'), float_format='%.6f')
print('\nparametros de f (f_parametros.csv):')
print(par.to_string(float_format=lambda x: '%.4f' % x))
print('\nOJO: f y b0 estan POR HORA. Para el ADRC en segundos, dividir ambos por 3600.')
