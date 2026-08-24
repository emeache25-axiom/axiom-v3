"""
AXIOM v3 — Motor de capacidades.
════════════════════════════════════════════════════════════════════════════════
Resuelve una capacidad: si es simple, la ejecuta; si es compuesta, resuelve sus
componentes y aplica la operación.

TRES COSAS QUE HACE Y NADIE TIENE QUE PEDIRLE:

  1. COMPONE LO EPISTÉMICO hacia arriba. Una compuesta hereda los límites de
     sus componentes y agrega los de su operación. Nadie escribe el mismo
     límite dos veces.

  2. REGISTRA EL ESTADO DE CADA PARTE. Si `regimen_btc` se calculó con 10 de 12
     señales, eso cambia la lectura y no puede quedar oculto. En v2 se escribía
     a mano; acá sale de la estructura.

  3. VERIFICA CONTRA LO DECLARADO. Si una capacidad declara que su valor va de
     0 a 100 y devuelve 71.349, eso se anota como advertencia. El valor no se
     descarta —puede ser legítimo— pero nadie puede ignorar que salió del rango
     que la propia capacidad declaró.

═══ EL CACHÉ ES TRANSPARENTE ═══════════════════════════════════════════════════

Quien llama no se entera de si el resultado se calculó o se sirvió. Pero LA
VIGENCIA SIEMPRE VIENE EN LA RESPUESTA: así nadie tiene que saber del caché y
nadie puede ignorar la frescura.

Ante un resultado vencido se devuelve el anterior MARCADO y se recalcula en
segundo plano. Mostrar el dato viejo solo es honesto si viene declarado desde
cuándo es — sin eso sería el problema que v2 tenía: datos viejos presentados
como actuales.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.nucleo.capacidades import (
    Capacidad, Simple, Compuesta, Resultado, RegistroCapacidades, registro)
from backend.nucleo.fallos import clasificar

logger = logging.getLogger(__name__)

# Cuántos niveles de composición se permiten. No hay razón para más, y un
# límite explícito evita que un error de declaración cuelgue el proceso.
PROFUNDIDAD_MAXIMA = 8


class MotorError(Exception):
    pass


class Motor:
    """
    Resuelve capacidades. Se instancia una vez con el registro y el contexto.

    `contexto` es lo que las capacidades necesitan para trabajar: el pool, el
    cliente de fuentes. El motor no sabe qué hay adentro — solo lo pasa.
    """

    def __init__(self, reg: RegistroCapacidades | None = None,
                 contexto: dict | None = None):
        self.registro = reg or registro
        self.contexto = contexto or {}
        # Qué se está calculando ahora. Evita que diez pedidos simultáneos de
        # lo mismo disparen diez cálculos.
        self._en_curso: dict[str, asyncio.Task] = {}

    # ── Lo único que se llama desde afuera ──────────────────────────────────
    async def resolver(self, nombre: str, args: dict | None = None,
                       _profundidad: int = 0) -> Resultado:
        if _profundidad > PROFUNDIDAD_MAXIMA:
            raise MotorError(
                f"composición de más de {PROFUNDIDAD_MAXIMA} niveles al "
                f"resolver '{nombre}' — probablemente hay un ciclo")

        cap = self.registro.obtener(nombre)
        args = self._validar_args(cap, args or {})

        if isinstance(cap, Compuesta):
            return await self._resolver_compuesta(cap, args, _profundidad)
        return await self._resolver_simple(cap, args)

    # ── Simples ─────────────────────────────────────────────────────────────
    async def _resolver_simple(self, cap: Simple, args: dict) -> Resultado:
        ahora = datetime.now(timezone.utc)
        valor = await cap.funcion(contexto=self.contexto, **args)

        # Una capacidad puede devolver el valor solo, o el valor con su
        # `fuente_hasta`. Lo segundo es preferible y lo primero es aceptable.
        fuente_hasta = None
        if isinstance(valor, dict) and "_fuente_hasta" in valor:
            fuente_hasta = valor.pop("_fuente_hasta")

        r = Resultado(
            capacidad=cap.nombre,
            valor=valor,
            calculado_at=ahora,
            fuente_hasta=fuente_hasta,
            vigente_hasta=self._vence(cap, ahora),
            vigente_evento=cap.vigencia.evento,
            mide=cap.epistemico.mide,
            infiere=cap.epistemico.infiere,
            no_sabe=[cap.epistemico.no_sabe] if cap.epistemico.no_sabe else [],
        )
        self._verificar_valor(cap, r)
        return r

    # ── Compuestas ──────────────────────────────────────────────────────────
    async def _resolver_compuesta(self, cap: Compuesta, args: dict,
                                  prof: int) -> Resultado:
        ahora = datetime.now(timezone.utc)
        op = self.registro._operaciones.get(cap.operacion)
        if op is None:
            raise MotorError(
                f"'{cap.nombre}' usa la operación '{cap.operacion}', "
                f"que no está registrada")

        # Los componentes se resuelven EN PARALELO: son independientes entre sí
        # y esperarlos en serie multiplicaría la latencia por su cantidad.
        async def uno(n: str):
            try:
                return n, await self.resolver(n, args, prof + 1), None
            except Exception as e:
                # Un componente que falla NO tumba la composición: se registra
                # como faltante y la operación decide si puede seguir. Un
                # régimen con 10 de 12 señales sigue siendo informativo; uno
                # con 2 de 12 no, y eso lo dice la operación, no el motor.
                logger.warning("[motor] %s ← %s falló (%s)",
                               cap.nombre, n, clasificar(e).value)
                return n, None, e

        crudos = await asyncio.gather(*[uno(n) for n in cap.componentes])

        partes: dict[str, Resultado] = {}
        faltantes: list[str] = []
        for nombre, res, err in crudos:
            if res is None:
                faltantes.append(nombre)
            else:
                partes[nombre] = res

        # La operación recibe QUÉ FALTÓ, no solo lo que llegó.
        #
        # Sin esto una operación calcula sobre lo que recibió y reporta
        # convicción plena: "3 de 3" cuando en realidad esperaba 4. La
        # diferencia importa — un régimen con 10 de 12 señales sigue siendo
        # informativo, uno con 2 de 12 no, y eso lo decide la operación, que es
        # la que conoce su propia lógica.
        valor = await op(
            partes=partes, pesos=cap.pesos, parametros=args,
            contexto=self.contexto,
            esperados=len(cap.componentes), faltantes=faltantes)

        # ── Lo epistémico se COMPONE, no se reescribe ───────────────────────
        # Los límites del DATO se heredan de los componentes; los del MÉTODO
        # los agrega la operación; y lo propio de esta composición lo declara
        # la capacidad. Nadie escribe el mismo límite dos veces.
        no_sabe: list[str] = []
        for n, p in partes.items():
            for l in p.no_sabe:
                etiquetado = f"{n}: {l}"
                if etiquetado not in no_sabe:
                    no_sabe.append(etiquetado)
        if cap.epistemico.no_sabe:
            no_sabe.insert(0, cap.epistemico.no_sabe)

        # La frescura de una compuesta es la de su componente MÁS VIEJO: decir
        # que se calculó recién cuando una de sus partes es de ayer sería
        # mentir por omisión.
        fuentes = [p.fuente_hasta for p in partes.values() if p.fuente_hasta]
        fuente_hasta = min(fuentes) if fuentes else None

        r = Resultado(
            capacidad=cap.nombre,
            valor=valor,
            calculado_at=ahora,
            fuente_hasta=fuente_hasta,
            vigente_hasta=self._vence(cap, ahora),
            vigente_evento=cap.vigencia.evento,
            mide=cap.epistemico.mide,
            infiere=cap.epistemico.infiere,
            no_sabe=no_sabe,
            componentes={
                "esperados": len(cap.componentes),
                "disponibles": len(partes),
                "detalle": {n: p.valor for n, p in partes.items()},
            },
            faltantes=faltantes,
        )

        if faltantes:
            r.advertencias.append(
                f"se calculó con {len(partes)} de {len(cap.componentes)} "
                f"componentes; faltaron: {', '.join(faltantes)}")

        self._verificar_valor(cap, r)
        return r

    # ── Verificaciones ──────────────────────────────────────────────────────
    def _validar_args(self, cap: Capacidad, args: dict) -> dict:
        """
        Los parámetros no declarados se rechazan.

        Un parámetro mal escrito que se ignora en silencio es un modo de falla
        real: en v2 un `dias` que nunca llegaba hacía que se devolviera siempre
        la ventana por defecto, y nadie se enteró durante meses.
        """
        if not cap.parametros:
            return {}
        sobrantes = set(args) - set(cap.parametros)
        if sobrantes:
            raise MotorError(
                f"'{cap.nombre}' no admite {sorted(sobrantes)}. "
                f"Admite: {sorted(cap.parametros)}")

        final = {}
        for nombre, spec in cap.parametros.items():
            v = args.get(nombre, spec.get("default"))
            if v is not None:
                if spec.get("min") is not None and v < spec["min"]:
                    raise MotorError(
                        f"'{cap.nombre}.{nombre}' = {v} es menor que el mínimo "
                        f"declarado ({spec['min']})")
                if spec.get("max") is not None and v > spec["max"]:
                    raise MotorError(
                        f"'{cap.nombre}.{nombre}' = {v} supera el máximo "
                        f"declarado ({spec['max']})")
            final[nombre] = v
        return final

    def _verificar_valor(self, cap: Capacidad, r: Resultado) -> None:
        """
        Contrasta el resultado con lo que la capacidad declaró.

        No descarta nada: un valor fuera de rango puede ser legítimo —una coin
        nueva puede subir 71.349 % de verdad— pero nadie puede ignorar que salió
        del rango que la propia capacidad declaró.
        """
        p = cap.propiedad

        # Lo NO COMPARABLE se advierte siempre, sea cual sea la forma del valor.
        # Antes solo se verificaba si era un número, y capacidades como
        # `repetibilidad` —que devuelve una curva— quedaban sin la advertencia
        # justo por ser las que más la necesitan.
        if not p.comparable:
            r.advertencias.append(
                f"NO comparable entre objetos: {p.por_que_no_comparable}")

        v = r.valor
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return
        if p.fuera_de_rango(v):
            r.advertencias.append(
                f"el valor {v} está fuera del rango declarado "
                f"[{p.minimo}, {p.maximo}]")

    @staticmethod
    def _vence(cap: Capacidad, ahora: datetime) -> datetime | None:
        if cap.vigencia.segundos is not None:
            return ahora + timedelta(seconds=cap.vigencia.segundos)
        return None      # vence por evento, no por tiempo

    # ── Explicación ─────────────────────────────────────────────────────────
    async def explicar(self, nombre: str) -> dict:
        """
        De qué se compone una respuesta, sin calcularla.

        Si una capacidad es una composición declarada, se puede mostrar de dónde
        salió: *"el régimen es alcista porque 8 de 12 señales votaron así"*. En
        v2 eso se escribía a mano; acá sale de la estructura.
        """
        cap = self.registro.obtener(nombre)
        return {
            "capacidad": nombre,
            "tipo": "compuesta" if cap.es_compuesta else "simple",
            "arbol": self.registro.arbol(nombre),
            "mide": cap.epistemico.mide,
            "infiere": cap.epistemico.infiere or None,
            "no_sabe": cap.epistemico.no_sabe,
            "vigencia": cap.vigencia.evento or f"{cap.vigencia.segundos}s",
        }
