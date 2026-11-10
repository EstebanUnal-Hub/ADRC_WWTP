# Tesis — Control con rechazo activo de perturbaciones para la regulación de OD en una PTAR

Fuente LaTeX del documento de tesis, con la estructura de la plantilla de
maestría de la Universidad Nacional (la misma de `Tesis1001219057.pdf`) y el
preámbulo de la propuesta.

## Compilar

```bash
latexmk -pdf main.tex          # o: pdflatex -> bibtex -> pdflatex x2
```

Salida: `main.pdf` (175 páginas, 77 entradas en la lista de figuras, 39 tablas, 39 referencias citadas).

## Archivos

| Archivo | Contenido |
|---|---|
| `main.tex` | Preámbulo, paquetes, geometría y orden de los capítulos |
| `secciones/00_portada.tex` | Portadas y dedicatoria |
| `secciones/01_resumen.tex` | Resumen y Abstract con palabras clave |
| `secciones/02_simbolos.tex` | Lista de símbolos y abreviaturas |
| `secciones/03_introduccion.tex` | Cap. 1: Introducción: justificación, estado del arte, problema, hipótesis, objetivos |
| `secciones/04_Caracterizacion.tex` | Cap. 2: Caracterización y modelado de la planta |
| `secciones/05_ADRC_ESO.tex` | Cap. 3: ADRC basado en observador de estado extendido (ESO) |
| `secciones/06_GPI.tex` | Cap. 4: Control proporcional-integral generalizado (GPI) robusto |
| `secciones/07_Aspectos_practicos_de_implementacion.tex` | Cap. 5: Aspectos prácticos de implementación: saturación, referencia, discretización, PLC |
| `secciones/08_Comparacion_PID.tex` | Cap. 6: Comparación PID ISA contra ADRC |
| `secciones/09_discusion.tex` | Cap. 7: Discusión |
| `secciones/10_conclusiones.tex` | Cap. 8: Conclusiones |
| `secciones/11_declaracion_ia.tex` | Declaración del uso de IA |
| `secciones/12_anexos.tex` | Anexo: tabla de los archivos principales, con enlaces al README del repositorio |
| `references.bib` | 39 entradas, todas citadas (sin diapositivas ni notas de clase); las principales (libros, Sira, Herbst y Madoński, Cortés-Romero) van primero con `\nocite` en `main.tex` |
| `figuras/` | Solo las figuras que usa el documento |

## De dónde sale cada número

Las rutas son relativas a la carpeta `PTAR/`.

- **Capítulo 2** (identificación, perturbaciones, caudales, ruido, segundo soplador):
  `Datos/analisis/analisis_dinamica_limpio.ipynb`. La celda 1 define el estilo común
  de las figuras.
- **Capítulos 3 a 6** (diseños del ADRC y del GPI, anti-windup, discretización, trazas
  del PLC en la celda 6.1, comparación con el PID, la Figura 6.5 en la celda 7.3b y la Figura 5.14,
  el prefiltro con la planta, en la última celda):
  `Simulaciones/PTAR/02 Diseño/Python/ADRC_PTAR_continuo.ipynb`. En las Figuras 6.4 y 6.5 el
  simulador no deja bajar el OD de 0 mg/L.
- **Discretización** (Bode de los métodos, ADRC y GPI discretos con retardo):
  `Simulaciones/PTAR/02 Diseño/Python/ADRC_PTAR_discreto.ipynb`.
- Los dos cuadernos buscan la carpeta `PTAR/` al arrancar (primeras líneas de la celda de
  importaciones), así que sus rutas siguen siendo relativas a `PTAR/` aunque estén en otra carpeta.
- **P&ID (Figura 2.1)**: `P&ID/P&ID.vsdx`, exportado a `P&ID/P&ID.pdf` y copiado como
  `figuras/pid_ptar.pdf`. El P&ID usa el lazo 100 (OD) y los lazos 101 y 102 (caudales).
- **Bloques del PLC**: `PLC_ST/Codigos/`; la librería documentada para ctrlX está en
  `PLC_ST/Libreria_ADRC/`.

## Figuras

`figuras/` contiene solo las figuras que cita el documento. Al correr completos los cuadernos
aparecen además figuras que no se usan y se pueden borrar: `ident_01_dos_dias_manual.pdf`,
`ident_04_histogramas_tau_K.pdf`, `ident_08_ganancia_vs_od.pdf` e `ident_15_ensayo_scada.pdf`
(capítulo 2), y `adrc_embrague.pdf` y `pid_rechazo_mejorado.pdf` (cuaderno continuo).

## Pendiente antes de entregar

1. Confirmar el título exacto del codirector (aparece como M.Sc. Harvey David
   Rojas Cala).
2. Revisar la dedicatoria, que es un texto de relleno.
3. Añadir, si el jurado lo pide, los índices oficiales del BSM1 (EQ, AE) y los
   influentes de lluvia y tormenta.
