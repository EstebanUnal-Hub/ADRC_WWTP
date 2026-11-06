#!/usr/bin/env python3
"""Convierte los historicos .hst / .hsz de InduSoft Web Studio a CSV/TXT.

Reemplaza la funcion Hst2Txt() de WinStudio. Ejemplos:

    # un CSV consolidado por grupo (por defecto)
    python3 hst2csv.py Hst -o salida

    # un archivo por cada .hst/.hsz, igual que Hst2Txt
    python3 hst2csv.py Hst -o salida --por-archivo

    # solo el grupo 05, entre dos fechas, separador ; y hora UTC
    python3 hst2csv.py Hst -o salida -g 05 --desde 2025-01-01 --hasta 2025-12-31 --sep ";" --utc
"""
import argparse, datetime, glob, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hstlib

# Los sellos de tiempo se guardan en UTC; la planta trabaja en UTC-5.
DESFASE_LOCAL = datetime.timedelta(hours=-5)


def nombre_grupo(path):
    return os.path.basename(path)[:2].lower()


def fecha_archivo(path):
    """GGYYMMDD.hst -> date(20YY, MM, DD)."""
    b = os.path.basename(path)[2:8]
    try:
        return datetime.date(2000 + int(b[:2]), int(b[2:4]), int(b[4:6]))
    except ValueError:
        return None


def recolectar(entradas, grupos, desde, hasta):
    """Une .hst y .hsz; si un dia existe en ambos formatos usa el .hst."""
    encontrados = {}
    for e in entradas:
        rutas = [e] if os.path.isfile(e) else sorted(
            glob.glob(os.path.join(e, '*.hst')) + glob.glob(os.path.join(e, '*.hsz')))
        for r in rutas:
            clave = os.path.splitext(os.path.basename(r))[0].lower()
            if grupos and nombre_grupo(r) not in grupos:
                continue
            f = fecha_archivo(r)
            if f and ((desde and f < desde) or (hasta and f > hasta)):
                continue
            if clave not in encontrados or r.lower().endswith('.hst'):
                encontrados[clave] = r
    return [encontrados[k] for k in sorted(encontrados)]


def fmt(v):
    if v != v or v in (float('inf'), float('-inf')):
        return ''
    return repr(round(v, 6)) if v % 1 else str(int(v))


def escribir(fh, tags, filas, sep, utc, cabecera=True):
    if cabecera:
        fh.write(sep.join(['Fecha_Hora'] + tags) + '\n')
    for ts, vals in filas:
        if not utc:
            ts = ts + DESFASE_LOCAL
        fh.write(sep.join([ts.strftime('%Y-%m-%d %H:%M:%S')] + [fmt(v) for v in vals]) + '\n')


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('entrada', nargs='+', help='carpeta(s) o archivo(s) .hst/.hsz')
    p.add_argument('-o', '--salida', default='csv', help='carpeta de salida (por defecto: csv)')
    p.add_argument('-g', '--grupo', action='append', default=[],
                   help='limitar a un grupo, p.ej. 05 (repetible)')
    p.add_argument('--desde', help='fecha minima AAAA-MM-DD')
    p.add_argument('--hasta', help='fecha maxima AAAA-MM-DD')
    p.add_argument('--sep', default=',', help='separador de columnas (por defecto: ,)')
    p.add_argument('--ext', default='csv', help='extension de salida: csv o txt')
    p.add_argument('--por-archivo', action='store_true',
                   help='un archivo de salida por cada .hst en vez de uno por grupo')
    p.add_argument('--utc', action='store_true',
                   help='dejar la hora en UTC (por defecto se pasa a hora local UTC-5)')
    a = p.parse_args()

    fecha = lambda s: datetime.datetime.strptime(s, '%Y-%m-%d').date() if s else None
    grupos = {g.lower() for g in a.grupo}
    archivos = recolectar(a.entrada, grupos, fecha(a.desde), fecha(a.hasta))
    if not archivos:
        sys.exit('No se encontraron archivos .hst/.hsz que coincidan.')
    os.makedirs(a.salida, exist_ok=True)
    print('%d archivos por convertir -> %s/' % (len(archivos), a.salida))

    # Un grupo puede cambiar su lista de tags con el tiempo (reconfiguracion del
    # SCADA); cada lista distinta va a su propio archivo _vN para no perder datos.
    abiertos, variantes, filas_tot, errores = {}, {}, 0, []
    try:
        for i, ruta in enumerate(archivos, 1):
            try:
                tags, filas = hstlib.parse(ruta)
            except Exception as exc:
                errores.append((ruta, exc))
                continue
            filas_tot += len(filas)
            if a.por_archivo:
                dest = os.path.join(a.salida, os.path.splitext(os.path.basename(ruta))[0] + '.' + a.ext)
                with open(dest, 'w') as fh:
                    escribir(fh, tags, filas, a.sep, a.utc)
            else:
                clave = (nombre_grupo(ruta), tuple(tags))
                if clave not in abiertos:
                    g = clave[0]
                    variantes[g] = variantes.get(g, 0) + 1
                    sufijo = '' if variantes[g] == 1 else '_v%d' % variantes[g]
                    dest = os.path.join(a.salida, 'grupo_%s_%s%s.%s'
                                        % (g, tags[0].split('[')[0], sufijo, a.ext))
                    abiertos[clave] = open(dest, 'w')
                    escribir(abiertos[clave], tags, [], a.sep, a.utc)
                escribir(abiertos[clave], tags, filas, a.sep, a.utc, cabecera=False)
            if i % 500 == 0 or i == len(archivos):
                print('  %d/%d (%d filas)' % (i, len(archivos), filas_tot), flush=True)
    finally:
        for fh in abiertos.values():
            fh.close()

    print('\nListo: %d filas escritas en %s/' % (filas_tot, a.salida))
    for f in sorted(os.listdir(a.salida))[:40]:
        print('  %-52s %10.1f MB' % (f, os.path.getsize(os.path.join(a.salida, f)) / 1e6))
    if errores:
        print('\n%d archivos con problemas:' % len(errores))
        for r, e in errores[:20]:
            print('  %s: %s' % (r, e))


if __name__ == '__main__':
    main()
