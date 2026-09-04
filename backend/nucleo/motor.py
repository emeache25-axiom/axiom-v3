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

import json
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.nucleo.capacidades import (
    Capacidad, Simple, Compuesta, Resultado, RegistroCapacidades, registro,
    Alcance)
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
        # Normaliza date->datetime(UTC) para comparar fuentes de granularidad
        # distinta. btc_estado fue la primera compuesta que mezcló una fuente
        # horaria (funding: datetime) con diarias (opciones, dominancia: date);
        # min() sobre esa mezcla lanzaba "can't compare datetime to date". El
        # key normaliza sólo para comparar: el valor devuelto conserva su tipo.
        def _a_dt(x):
            if isinstance(x, datetime):
                return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
            return datetime(x.year, x.month, x.day, tzinfo=timezone.utc)
        fuentes = [p.fuente_hasta for p in partes.values() if p.fuente_hasta]
        fuente_hasta = min(fuentes, key=_a_dt) if fuentes else None

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

    # ── Vigencia ────────────────────────────────────────────────────────────
    async def vigente(self, nombre: str, objeto_id: str | None = None,
                      args: dict | None = None) -> tuple[bool, Any]:
        """
        ¿Hay un valor guardado que todavía valga? Devuelve (vigente, valor).

        Dos formas de vencer, y la distinción importa:

          · POR TIEMPO — `vigente_hasta` contra ahora. Para lo que cambia
            continuamente: precio, spread. No hay evento discreto que lo
            invalide.

          · POR EVENTO — se compara contra CUÁNDO OCURRIÓ el evento por última
            vez. Si el valor se calculó antes del último cierre de vela, está
            vencido aunque se haya calculado hace un minuto.

        Lo segundo es lo correcto y por eso hizo falta la tabla `eventos`: el
        bus vive en memoria y un reinicio lo borra.
        """
        pool = self.contexto.get("pool")
        if pool is None:
            return False, None
        cap = self.registro.obtener(nombre)

        async with pool.acquire() as conn:
            fila = await conn.fetchrow("""
                SELECT valor_num, valor_json, calculado_at, vigente_hasta,
                       advertencias
                FROM valores
                WHERE capacidad = $1 AND args = $2::jsonb
                  AND ($3::text IS NULL OR objeto_id = $3)
                ORDER BY calculado_at DESC LIMIT 1
            """, nombre, json.dumps(args or {}), objeto_id)

            if fila is None:
                return False, None

            valor = (float(fila["valor_num"]) if fila["valor_num"] is not None
                     else (json.loads(fila["valor_json"]) if fila["valor_json"] else None))

            if cap.vigencia.segundos is not None:
                v = (fila["vigente_hasta"] is not None
                     and fila["vigente_hasta"] > datetime.now(timezone.utc))
                return v, valor

            if cap.vigencia.evento:
                ultimo = await conn.fetchval(
                    "SELECT MAX(ocurrido_at) FROM eventos WHERE tipo = $1",
                    cap.vigencia.evento)
                # Sin registro del evento no se puede afirmar que esté vigente.
                # Ante la duda, recalcular: es preferible pagar el cálculo a
                # servir un dato que quizá esté viejo.
                if ultimo is None:
                    return False, valor
                return fila["calculado_at"] >= ultimo, valor

        return False, valor

    # ── Persistencia ────────────────────────────────────────────────────────
    async def persistir(self, r: Resultado, args: dict | None = None) -> int:
        """
        Guarda el resultado en `valores`.

        Una capacidad MASIVA devuelve todos los objetos de una vez y se
        desagrega en una fila por objeto: es lo que permite que el screener
        filtre y ordene. Una INDIVIDUAL es una sola fila.

        La desagregación se hace porque la capacidad declaró que es masiva, no
        porque el motor adivine la forma del resultado.
        """
        pool = self.contexto.get("pool")
        if pool is None:
            return 0
        cap = self.registro.obtener(r.capacidad)
        args = args or {}

        if cap.alcance is Alcance.MASIVA:
            por_objeto = (r.valor or {}).get("por_par") or (r.valor or {}).get("por_objeto") or {}
            filas = []
            for objeto_id, d in por_objeto.items():
                v = d.get("valor") if isinstance(d, dict) else d
                # Los parámetros del cálculo son parte de la clave: el mismo
                # rango con ventana 30 y con 90 son valores DISTINTOS, no uno
                # que pisa al otro.
                clave_args = {k: v2 for k, v2 in args.items() if k != "par_id"}
                filas.append((
                    r.capacidad, cap.objeto.value, str(objeto_id),
                    json.dumps(clave_args),
                    float(v) if isinstance(v, (int, float)) else None,
                    json.dumps(v, default=str) if not isinstance(v, (int, float)) else None,
                    r.calculado_at, r.fuente_hasta, r.vigente_hasta,
                    r.vigente_evento or None,
                    # La ventana incompleta viaja como advertencia POR OBJETO:
                    # una métrica sobre 9 velas no es comparable con una sobre
                    # 30, y sin esto se ven idénticas.
                    json.dumps(
                        [] if (not isinstance(d, dict) or d.get("ventana_completa", True))
                        else [f"ventana incompleta: {d.get('velas')} velas de "
                              f"{r.valor.get('ventana_pedida')}"]),
                ))
        else:
            # Una capacidad individual puede devolver el número solo, o un
            # dict que lo acompaña con su percentil y su procedencia. En el
            # segundo caso el número está en la clave `valor`, y hay que
            # sacarlo: `valor_num` es la columna INDEXADA para filtrar y
            # ordenar, y dejar el número dentro del JSON lo vuelve
            # incomparable — que es justo para lo que sirve la tabla.
            crudo = r.valor
            num = crudo
            if isinstance(crudo, dict):
                num = crudo.get("valor")
            es_num = isinstance(num, (int, float)) and not isinstance(num, bool)

            filas = [(
                r.capacidad, cap.objeto.value,
                str(args.get("objeto_id") or args.get("par_id")
                    or cap.objeto.value),
                json.dumps(args),
                float(num) if es_num else None,
                # El JSON se guarda igual cuando hay estructura además del
                # número: el percentil y la procedencia no se pierden.
                json.dumps(crudo, default=str) if isinstance(crudo, dict) else None,
                r.calculado_at, r.fuente_hasta, r.vigente_hasta,
                r.vigente_evento or None, json.dumps(r.advertencias),
            )]

        if not filas:
            return 0
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO valores (capacidad, objeto, objeto_id, args,
                    valor_num, valor_json, calculado_at, fuente_hasta,
                    vigente_hasta, vigente_evento, advertencias)
                VALUES ($1,$2,$3,$4::jsonb,$5,$6::jsonb,$7,$8,$9,$10,$11::jsonb)
                ON CONFLICT (capacidad, objeto, objeto_id, args) DO UPDATE SET
                    valor_num      = EXCLUDED.valor_num,
                    valor_json     = EXCLUDED.valor_json,
                    calculado_at   = EXCLUDED.calculado_at,
                    fuente_hasta   = EXCLUDED.fuente_hasta,
                    vigente_hasta  = EXCLUDED.vigente_hasta,
                    vigente_evento = EXCLUDED.vigente_evento,
                    advertencias   = EXCLUDED.advertencias
            """, filas)
        logger.info("[motor] %s → %d valores persistidos", r.capacidad, len(filas))
        return len(filas)

    async def recalcular_masivas(self, evento: str) -> dict:
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
                continue
            try:
                r = await self.resolver(cap.nombre)
                hechas[cap.nombre] = await self.persistir(r, {})
            except Exception as e:
                logger.error("[motor] %s falló al recalcular: %s", cap.nombre, e)
                fallidas[cap.nombre] = f"{clasificar(e).value}: {e}"[:200]
        return {"evento": evento, "recalculadas": hechas,
                "fallidas": fallidas or None}

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
