"""Lectura de archivos historicos de InduSoft Web Studio (.hst / .hsz)."""
import struct, datetime

FILETIME_EPOCH = datetime.datetime(1601, 1, 1)


def lzw_decompress(data, expected=None, base=259):
    """LZW propietario de InduSoft: MSB-first, ancho variable desde 9 bits.
    Codigos reservados: 257 = aumentar ancho, 258 = reiniciar diccionario."""
    out = bytearray()
    dic = {i: bytes([i]) for i in range(256)}
    nxt, width = base, 9
    acc = nbits = 0
    prev = None
    for byte in data:
        acc = (acc << 8) | byte
        nbits += 8
        while nbits >= width:
            nbits -= width
            code = (acc >> nbits) & ((1 << width) - 1)
            acc &= (1 << nbits) - 1
            if code == 257:
                width += 1
                continue
            if code == 258:
                dic = {i: bytes([i]) for i in range(256)}
                nxt, width, prev = base, 9, None
                continue
            if code in dic:
                entry = dic[code]
            elif code == nxt and prev is not None:
                entry = prev + prev[:1]
            else:
                raise ValueError('codigo LZW invalido %d (nxt=%d, ancho=%d, salida=%d)'
                                 % (code, nxt, width, len(out)))
            out += entry
            if prev is not None:
                dic[nxt] = prev + entry[:1]
                nxt += 1
            prev = entry
            if expected is not None and len(out) >= expected:
                return bytes(out[:expected])
    return bytes(out)


def read_raw(path):
    """Devuelve el contenido .hst descomprimiendo si el archivo es .hsz."""
    with open(path, 'rb') as fh:
        data = fh.read()
    if data[:8] == b'**++LZW ':
        raw_len, comp_len = struct.unpack_from('<II', data, 8)
        out = lzw_decompress(data[16:16 + comp_len], raw_len)
        if len(out) != raw_len:
            raise ValueError('%s: LZW incompleto (%d de %d bytes)' % (path, len(out), raw_len))
        return out
    if data[:8].startswith(b'**++'):
        raise ValueError('%s: compresion no soportada: %r' % (path, data[4:8]))
    return data


def parse(path):
    """-> (lista_de_tags, lista_de_filas). Cada fila es (datetime_utc, [valores])."""
    d = read_raw(path)
    ver, data_off, rec_size, names_len = struct.unpack_from('<4H', d, 0)
    ntags = struct.unpack_from('<H', d, 0x44)[0]
    if ver != 3 or 8 + 8 * ntags != rec_size or 0x46 + names_len != data_off:
        raise ValueError('%s: cabecera inesperada v%d off=%d rec=%d n=%d'
                         % (path, ver, data_off, rec_size, ntags))
    campos = d[0x46:0x46 + names_len].decode('latin-1').split('\t \t')
    tags = [c for c in campos if c][:ntags]
    nrec = (len(d) - data_off) // rec_size
    filas = []
    for i in range(nrec):
        o = data_off + i * rec_size
        ticks = struct.unpack_from('<Q', d, o)[0]
        if ticks == 0:
            continue
        ts = FILETIME_EPOCH + datetime.timedelta(microseconds=ticks // 10)
        filas.append((ts, list(struct.unpack_from('<%dd' % ntags, d, o + 8))))
    return tags, filas
