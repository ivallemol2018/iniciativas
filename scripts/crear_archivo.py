#!/usr/bin/env python3
"""
Detecta archivos Excel subidos con patrón *_Dxxxx y crea la carpeta correspondiente.
Uso: python scripts/crear_carpeta.py archivo1.xlsx archivo2.xls ...
"""

import sys
import re
import os

PATRON = re.compile(r'D\d{4}')

def procesar_archivo(ruta_archivo: str) -> str | None:
    """Detecta el código Dxxxx en el nombre del archivo y crea la carpeta."""
    nombre = os.path.basename(ruta_archivo)
    match = PATRON.search(nombre)

    if not match:
        print(f"[SKIP] No se encontró patrón Dxxxx en: {nombre}")
        return None

    codigo = match.group(0)
    os.makedirs(codigo, exist_ok=True)

    # Mantiene la carpeta versionada aunque esté vacía
    gitkeep_path = os.path.join(codigo, ".gitkeep")
    if not os.path.exists(gitkeep_path):
        open(gitkeep_path, "w").close()

    # Descomentar si se quiere mover el excel a su carpeta
    # destino = os.path.join(codigo, nombre)
    # os.replace(ruta_archivo, destino)

    print(f"[OK] Carpeta creada/asegurada: {codigo} (desde {nombre})")
    return codigo

def main():
    archivos = sys.argv[1:]

    if not archivos:
        print("No se recibieron archivos para procesar.")
        sys.exit(0)

    carpetas_creadas = []
    for archivo in archivos:
        if not archivo.strip():
            continue
        resultado = procesar_archivo(archivo.strip())
        if resultado:
            carpetas_creadas.append(resultado)

    print(f"\nResumen: {len(carpetas_creadas)} carpeta(s) procesada(s): {carpetas_creadas}")

if __name__ == "__main__":
    main()