"""Clasifica el regimen de operacion de cada modulo dia a dia.

Distingue lazo cerrado (PID) de operacion manual a partir de tres huellas:
  - el error de seguimiento y cuantas veces la PV cruza la consigna,
  - cuanto se aleja el OD por encima de la consigna,
  - si el soplador modula o esta clavado (en el maximo o en cero).
"""
import numpy as np, pandas as pd


def cruces(e):
    """Numero de cambios de signo del error, ignorando la banda muerta del ruido."""
    s = np.sign(e.where(e.abs() > 0.05))
    s = s.dropna()
    return int((s.diff() != 0).sum() - 1) if len(s) > 1 else 0


def rasgos_dia(od, sp, u):
    """Resumen de un dia para un modulo. od/sp/u son series de 1 min."""
    r = {}
    v = od.dropna()
    r['n'] = len(v)
    if len(v) < 60:
        return r
    r['od_med'] = v.mean(); r['od_std'] = v.std()
    r['od_max'] = v.max(); r['od_p95'] = v.quantile(.95)
    r['frac_alto'] = (v > 5).mean()      # muy por encima de cualquier consigna
    r['frac_cero'] = (v < 0.1).mean()
    s = sp.dropna()
    r['sp_med'] = s.median() if len(s) else np.nan
    r['sp_cambios'] = int((s.diff().abs() > 0.02).sum()) if len(s) else 0
    e = (od - sp).dropna()
    if len(e):
        r['iae'] = e.abs().mean()
        r['cruces'] = cruces(e)
    if u is not None:
        w = u.dropna()
        if len(w) > 60:
            r['u_med'] = w.mean(); r['u_std'] = w.std(); r['u_max'] = w.max()
            top = w.quantile(.99)
            r['frac_umax'] = (w > 0.95 * top).mean() if top > 5 else np.nan
            r['frac_uoff'] = (w < 1).mean()
    return r


def etiquetar(r, u_nominal):
    """Regla de decision sobre los rasgos de un dia."""
    if r.get('n', 0) < 60:
        return 'sin_datos'
    if r.get('frac_cero', 0) > 0.9:
        return 'od_cero'
    u_med, u_std = r.get('u_med'), r.get('u_std')
    if u_med is not None and not np.isnan(u_med):
        if r.get('frac_uoff', 0) > 0.9:
            return 'soplador_apagado'
        # soplador clavado arriba y OD disparado = lazo abierto al maximo
        if r.get('frac_umax', 0) > 0.5 and r.get('frac_alto', 0) > 0.3:
            return 'manual_maximo'
        if u_std is not None and u_std < 0.05 * max(u_nominal, 1):
            return 'manual_fijo'
    sp = r.get('sp_med', 0)
    if sp and sp > 0.05:
        if r.get('frac_alto', 0) > 0.5:
            return 'manual_maximo'
        if r.get('cruces', 0) >= 6 and r.get('iae', 9) < 0.6 * sp:
            return 'pid'
        if r.get('iae', 9) < 0.35 * sp:
            return 'pid'
    return 'manual'


def tabla(ox, sop):
    """DataFrame indexado por (modulo, dia) con rasgos y etiqueta.

    Une OD y soplador en una sola rejilla: los grupos del historiador no
    comparten exactamente los mismos sellos de tiempo.
    """
    d = ox.join(sop, how='outer')
    dia_idx = d.index.normalize()
    filas = []
    for mod in ('M1', 'M2', 'M3'):
        col_u = mod + '_pot'
        u_nom = d[col_u].quantile(.99) if col_u in d else 1
        for dia, g in d.groupby(dia_idx):
            r = rasgos_dia(g[mod + '_od'], g[mod + '_sp'],
                           g[col_u] if col_u in g else None)
            r['modulo'] = mod; r['dia'] = dia.date()
            r['regimen'] = etiquetar(r, u_nom)
            filas.append(r)
    return pd.DataFrame(filas).set_index(['modulo', 'dia']).sort_index()
