"""Carga y limpieza de los historicos del SCADA de la PTAR de Tunja."""
import numpy as np, pandas as pd, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(BASE, 'csv')

# grupo -> archivo
G = {
    '01': 'grupo_01_M2_SENSOR_ALTURA_E_1.csv',
    '02': 'grupo_02_M2_SENSOR_PRESION_SOP_1.csv',
    '03': 'grupo_03_M2_SENSOR_CAUDAL12IN.csv',
    '04': 'grupo_04_M2_VOLTAJE_L12.csv',
    '05': 'grupo_05_M2_VOLTAJE_L12.csv',
    '06': 'grupo_06_M2_VOLTAJE_L12.csv',
    '07': 'grupo_07_M2_SENSOR_OXIGENO_1.csv',
    '08': 'grupo_08_M3_SENSOR_ALTURA_TL.csv',
    '09': 'grupo_09_M3_SENSOR_PRESION_SOP_1.csv',
    '0a': 'grupo_0a_M3_SENSOR_CAUDAL_PARSHALL.csv',
    '0b': 'grupo_0b_M3_VOLTAJE_L12.csv',
    '0c': 'grupo_0c_M3_VOLTAJE_L12.csv',
    '0d': 'grupo_0d_M3_VOLTAJE_L12.csv',
    '0e': 'grupo_0e_M3_PROMEDIO_OXIGENO.csv',
    '0f': 'grupo_0f_BARRELODOSGENERAL_VOLTAJE_L12.csv',
    '10': 'grupo_10_CAUDALIMETRO_ENTRADA_v2.csv',
    '11': 'grupo_11_M1_OXIGENOPROMEDIO.csv',
    '12': 'grupo_12_M1_SOPLADOR_1_PRESION.csv',
}

# El sensor de OD satura en 10 mg/L; por encima de eso el registro es basura.
OD_MAX = 10.0


def leer(grupo, cols=None):
    d = pd.read_csv(os.path.join(CSV, G[grupo]), parse_dates=['Fecha_Hora'],
                    usecols=(['Fecha_Hora'] + cols) if cols else None)
    d = d.set_index('Fecha_Hora').sort_index()
    # el historiador repite algun sello de tiempo tras un reinicio del SCADA
    return d[~d.index.duplicated(keep='first')]


def limpiar(s, lo, hi):
    """Deja NaN donde el registro esta fuera del rango fisico del instrumento."""
    return s.where((s >= lo) & (s <= hi))


def oxigeno():
    """DataFrame a 1 min con OD y consigna de los tres modulos.

    La variable controlada es el promedio que calcula el PLC, que es la senal
    que realimenta el PID. Se usa ese tag tal cual; solo donde el registro esta
    corrupto (M2, feb-may 2025) se rellena con (od1+od2)/2. Ambos coinciden:
    verificado corr = 0,9996, RMSE 0,05 mg/L, y la diferencia se explica por el
    jitter de muestreo del historiador (cada tag se captura en un instante
    distinto dentro del minuto).
    """
    d = pd.DataFrame(index=leer('11').index)
    for mod, g, s1, s2, prom, sp in [
            ('M1', '11', 'M1_OXIGENO_1', 'M1_OXIGENO_2',
             'M1_OXIGENOPROMEDIO', 'M1_OXIGENOSETPOINT'),
            ('M2', '07', 'M2_SENSOR_OXIGENO_1', 'M2_SENSOR_OXIGENO_2',
             'M2_PROMEDIO_OXIGENO_SOPLADORES', 'M2_SETPOINT_OXIGENO_AIREACION'),
            ('M3', '0e', 'M3_SENSOR_OXIGENO_1', 'M3_SENSOR_OXIGENO_2',
             'M3_PROMEDIO_OXIGENO', 'M3_SETPOINT_OXIGENO_AIREACION')]:
        src = leer(g)
        a = limpiar(src[s1], 0, OD_MAX)
        b = limpiar(src[s2], 0, OD_MAX)
        d[mod + '_od1'] = a
        d[mod + '_od2'] = b
        # variable controlada = promedio del PLC, con respaldo recalculado
        d[mod + '_od'] = limpiar(src[prom], 0, OD_MAX).fillna((a + b) / 2)
        d[mod + '_sp'] = limpiar(src[sp], 0, OD_MAX)
    return d


def sopladores():
    """Potencia activa del soplador principal de M2 y M3, a 1 min (proxy de u)."""
    m2 = leer('04', ['M2_POTENCIA_ACTIVA_TOTAL[0]', 'M2_CORRIENTE_L1[0]'])
    m3 = leer('0b', ['M3_POTENCIA_ACTIVA_TOTAL[2]', 'M3_CORRIENTE_L1[2]'])
    d = pd.DataFrame(index=m2.index)
    d['M2_pot'] = limpiar(m2['M2_POTENCIA_ACTIVA_TOTAL[0]'], 0, 200)
    d['M2_corr'] = limpiar(m2['M2_CORRIENTE_L1[0]'], 0, 300)
    d['M3_pot'] = limpiar(m3['M3_POTENCIA_ACTIVA_TOTAL[2]'], 0, 200)
    d['M3_corr'] = limpiar(m3['M3_CORRIENTE_L1[2]'], 0, 300)
    return d


def horarios():
    """Caudales, niveles y presiones: registro horario."""
    d = pd.concat([
        leer('0a')[['M3_SENSOR_CAUDAL_PARSHALL', 'M3_SENSOR_CAUDAL12IN']],
        leer('03')[['M2_SENSOR_CAUDAL12IN', 'M2_SENSOR_FLUJO_DA']],
        leer('10')[['CAUDALIMETRO_SALIDA']],
        leer('01'), leer('08'),
        leer('12')[['M1_SOPLADOR_1_PRESION', 'M1_SOPLADOR_3_PRESION']],
        leer('02')[['M2_SENSOR_PRESION_SOP_1', 'M2_SENSOR_PRESION_SOP_2', 'M2_SENSOR_PRESION_SOP_3']],
        leer('09')[['M3_SENSOR_PRESION_SOP_1', 'M3_SENSOR_PRESION_SOP_2', 'M3_SENSOR_PRESION_SOP_3']],
    ], axis=1)
    for c in d.columns:
        d[c] = limpiar(d[c], 0, 1000 if 'CAUDAL' in c else 100)
    return d


# Hitos de los informes de servicio en sitio (carpeta Informes/)
HITOS = [
    ('2024-11-27', 'PID implementado en M1'),
    ('2025-04-14', 'PID configurado en M2 y M3'),
    ('2025-06-03', 'Seguimiento del PID'),
    ('2026-03-12', 'Control remoto desactivado'),
    ('2026-06-02', 'Revision IoT PR21'),
]


def vivo(s, minutos=30):
    """Mascara de muestras con instrumento vivo.

    Un sensor de OD sano nunca da dos lecturas identicas seguidas: el ruido
    propio es de ~0,007 mg/L. Si el valor no cambia durante `minutos`, la
    entrada analogica esta trabada o desconectada y el dato no sirve.
    """
    quieto = s.diff().abs().fillna(0) < 1e-9
    # longitud de la racha de valores repetidos a la que pertenece cada muestra
    grupo = (~quieto).cumsum()
    racha = quieto.groupby(grupo).transform('sum')
    return s.notna() & (racha < minutos)


def oxigeno_vivo():
    """oxigeno() con las muestras de instrumento trabado puestas a NaN."""
    d = oxigeno()
    for mod in ('M1', 'M2', 'M3'):
        m = vivo(d[mod + '_od'])
        for c in (mod + '_od', mod + '_od1', mod + '_od2'):
            d[c] = d[c].where(m)
        d[mod + '_vivo'] = m
    return d
