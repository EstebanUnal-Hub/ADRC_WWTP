# Conversión de históricos InduSoft (.hst / .hsz) sin WinStudio

Reemplaza la función `$Hst2Txt()` de InduSoft Web Studio que usabas en `formato.txt`.
Solo requiere Python 3, sin dependencias.

## Uso

```bash
# Un CSV consolidado por grupo (lo que ya se generó en ../csv/)
python3 tools/hst2csv.py Hst -o csv

# Un archivo por cada .hst/.hsz, como hacía Hst2Txt
python3 tools/hst2csv.py Hst -o csv --por-archivo

# Filtrar grupo y fechas, cambiar separador, dejar hora UTC
python3 tools/hst2csv.py Hst -o csv -g 05 --desde 2025-01-01 --hasta 2025-12-31 --sep ";" --utc
```

Desde Python:

```python
import hstlib
tags, filas = hstlib.parse('Hst/05251201.hsz')   # filas = [(datetime_utc, [valores]), ...]
```

## Formato de archivo (ingeniería inversa, verificado)

Nombre: `GGYYMMDD.hst`, donde `GG` es el número de grupo en hexadecimal y `YYMMDD`
la fecha local. Cada archivo cubre un día calendario local.

Cabecera (little-endian):

| Offset | Tipo  | Contenido                                        |
|--------|-------|--------------------------------------------------|
| 0x00   | u16   | versión de formato (siempre 3)                    |
| 0x02   | u16   | offset donde empiezan los datos                   |
| 0x04   | u16   | tamaño de registro = 8 + 8 × n_tags               |
| 0x06   | u16   | longitud del bloque de nombres                    |
| 0x44   | u16   | número de tags                                    |
| 0x46   | texto | nombres separados por `TAB espacio TAB`           |

Datos: registros consecutivos de `tamaño de registro` bytes, cada uno con un
`FILETIME` de Windows en UTC (u64, 100 ns desde 1601-01-01) seguido de un
`float64` por tag. Un timestamp en cero significa registro vacío.

La planta trabaja en UTC-5, por eso el conversor resta 5 horas salvo con `--utc`.

## Formato `.hsz` (comprimido)

Es el mismo `.hst` comprimido. Cabecera de 16 bytes:
`**++LZW ` (8 bytes) + `u32` tamaño original + `u32` tamaño comprimido.

El payload es LZW propietario: códigos MSB-first de ancho variable a partir de
9 bits, diccionario que arranca en el código **259**, y dos códigos de control:

- `257` → aumentar el ancho de código en 1 bit
- `258` → reiniciar el diccionario y volver a 9 bits

Verificado contra los 1773 días que existen en ambos formatos: la
descompresión reproduce el `.hst` byte a byte en los 1773 casos.
