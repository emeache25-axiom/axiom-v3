#!/usr/bin/env python3
"""
AXIOM v3 — Lo que se precalcula lo decide la VIGENCIA, no el alcance.

EL PROBLEMA:
  `recalcular_masivas` solo procesaba capacidades con alcance MASIVA. Las cinco
  del perfil de BTC son INDIVIDUAL —BTC es un solo objeto, no hay universo que
  recorrer— así que quedaban afuera: ni se recalculaban al cerrar el día ni se
  persistían en `valores`.

  Sin eso el perfil no acumula historia, y no se puede responder "cómo cambió
  el estado de BTC en el último mes".

EL ARREGLO, y es de significado más que de código:

  `Alcance` describe la FORMA del resultado —uno o muchos objetos—, y eso es
  todo lo que debería decir.

  Lo que decide el PRECÁLCULO es tener una vigencia por evento: si una
  capacidad declara que vence con el cierre de la vela diaria, es porque quiere
  recalcularse ahí. No hace falta un concepto nuevo — la vigencia ya dice
  cuándo deja de valer, y usarla también para saber cuándo recalcular es
  coherente.

  La clasificación original mezclaba las dos cosas: usé la forma del dato para
  decidir su ciclo de vida.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_precalculo_por_vigencia.py
    python3 scripts/parche_precalculo_por_vigencia.py --revertir
"""
from __future__ import annotations

import sys
import shutil
import argparse
import py_compile
from pathlib import Path
from datetime import datetime

DESTINO = Path("backend/nucleo/motor.py")

VIEJO = '''    async def recalcular_masivas(self, evento: str) -> dict:
        """
        Recalcula y persiste todas las capacidades masivas que dependen de un
        evento.

        Es lo que el bus dispara al cerrar el día: las capacidades no se
        suscriben una por una, se declaran con su vigencia y el motor las
        agrupa.
        """
        hechas, fallidas = {}, {}
        for cap in self.registro._caps.values():
            if cap.alcance is not Alcance.MASIVA:
                continue
            if cap.vigencia.evento != evento:
                continue'''

NUEVO = '''    async def recalcular_masivas(self, evento: str) -> dict:
        """
        Recalcula y persiste todo lo que depende de un evento.

        LO QUE DECIDE EL PRECÁLCULO ES LA VIGENCIA, NO EL ALCANCE.

        Si una capacidad declara que vence con `cierre_vela_diaria`, es porque
        quiere recalcularse ahí — sea de un objeto o de tres mil. `Alcance`
        describe la FORMA del resultado y no debería decidir su ciclo de vida.

        La versión anterior filtraba por `Alcance.MASIVA` y dejaba afuera al
        perfil de BTC, que es de un solo objeto: no se recalculaba ni se
        persistía, así que no acumulaba historia.

        Las capacidades no se suscriben una por una: se declaran con su
        vigencia y el motor las agrupa.
        """
        hechas, fallidas = {}, {}
        for cap in self.registro._caps.values():
            if cap.vigencia.evento != evento:
                continue'''


def revertir() -> int:
    bks = sorted(DESTINO.parent.glob(f"{DESTINO.name}.bak.*"))
    if not bks:
        print("No hay backups."); return 1
    shutil.copy2(bks[-1], DESTINO)
    print(f"Restaurado desde {bks[-1]}")
    return 0


def main() -> int:
    if not DESTINO.exists():
        print(f"ERROR: no se encuentra {DESTINO}.", file=sys.stderr); return 1

    src = DESTINO.read_text()

    if "LO QUE DECIDE EL PRECÁLCULO ES LA VIGENCIA" in src:
        print("Ya está aplicado. Nada que hacer.")
        return 0
    if VIEJO not in src:
        print("ERROR: el método no tiene la forma esperada. No se tocó nada.",
              file=sys.stderr)
        return 1

    src = src.replace(VIEJO, NUEVO, 1)
    cambios = ["el precálculo ahora lo decide la vigencia, no el alcance"]

    # ── 2. Un id legible para las capacidades de un solo objeto ─────────────
    # `objeto_id = "-"` funciona pero es opaco. Para una capacidad del mercado
    # el objeto ES Bitcoin, y decirlo hace la tabla legible sin consultar nada.
    viejo_id = '''                str(args.get("objeto_id") or args.get("par_id") or "-"),'''
    nuevo_id = '''                str(args.get("objeto_id") or args.get("par_id")
                    or cap.objeto.value),'''
    if viejo_id in src:
        src = src.replace(viejo_id, nuevo_id, 1)
        cambios.append("objeto_id legible en vez de '-'")

    # ── 3. Serializar fechas ────────────────────────────────────────────────
    # `json.dumps` sin `default=str` revienta si al resultado se le cuela un
    # date o un Decimal. Ya pasó con `oscilacion`, donde GREATEST devolvía
    # Decimal y rompía la persistencia. Es barato prevenirlo.
    antes = src.count("json.dumps(r.valor)")
    src = src.replace("json.dumps(r.valor)", "json.dumps(r.valor, default=str)")
    if antes:
        cambios.append(f"default=str en {antes} json.dumps del valor")
    antes2 = src.count("json.dumps(v) if not isinstance")
    src = src.replace("json.dumps(v) if not isinstance",
                      "json.dumps(v, default=str) if not isinstance")
    if antes2:
        cambios.append("default=str en el valor por objeto")

    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DESTINO.with_suffix(f".py.bak.{sello}")
    shutil.copy2(DESTINO, backup)
    DESTINO.write_text(src)

    try:
        py_compile.compile(str(DESTINO), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(backup, DESTINO)
        print(f"ERROR de sintaxis: {e}\\nSe restauró el backup.", file=sys.stderr)
        return 1

    print(f"Backup: {backup}")
    for c in cambios:
        print(f"  ~ {c}")
    print("\\nOK. Ahora:  sudo systemctl restart axiom-v3")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    sys.exit(revertir() if a.revertir else main())
