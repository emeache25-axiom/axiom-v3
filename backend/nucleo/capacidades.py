"""
AXIOM v3 — Registro de capacidades.
════════════════════════════════════════════════════════════════════════════════
Una capacidad es algo que el sistema sabe. Hay dos clases:

    SIMPLE      mide algo directamente
                `rango_tipico`, `btc_dominance`, `amplitud`

    COMPUESTA   combina otras mediante una OPERACIÓN
                `regimen_btc` = doce señales combinadas por *clasificar*

El modelo es recursivo: una compuesta puede componer simples, compuestas, o
cualquier mezcla. Sin límite de niveles.

═══ POR QUÉ ESTO RESUELVE LO EPISTÉMICO ════════════════════════════════════════

Fue lo que más costó cerrar del diseño. La pregunta era: si una capacidad es una
composición, ¿cómo se compone su declaración de qué mide, qué infiere y qué no
sabe?

**No hay que inventar reglas: la composición es de capacidades, y las
capacidades ya saben declararse.**

Una compuesta HEREDA los límites de sus componentes y AGREGA los propios de su
operación. Que `btc_dominance` sea un ratio y no diga si el mercado crece se
declara UNA sola vez, en la señal, y viaja a todas las composiciones que la usen.

═══ DECLARACIÓN MIXTA: ESTRUCTURADA Y LIBRE ════════════════════════════════════

En v2 lo epistémico era texto libre. Flexible y legible, pero nada garantizaba
que estuviera completo ni era verificable.

Acá conviven las dos formas:

  · ESTRUCTURADO lo que el sistema puede verificar — unidad, rango válido,
    dirección, neutro medido. Con eso se detecta un valor imposible y se sabe
    si dos capacidades son comparables entre sí.

  · LIBRE lo que solo se explica — *"el rango es el DISPONIBLE, no el
    capturable: no descuenta spread ni deslizamiento"*. Eso no se estructura,
    y es exactamente lo que evita que alguien lea mal el número.

═══ SE VERIFICA AL ARRANCAR ════════════════════════════════════════════════════

Una capacidad sin declaración epistémica no se registra: falla al importar. En
v2 el registro hacía lo mismo con los widgets y funcionaba — es preferible que
el servicio no levante a que responda con una capacidad que no declara qué
mide.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


class Objeto(str, Enum):
    """Sobre qué aplica una capacidad. Restringe las composiciones válidas."""
    COIN = "coin"
    PAR = "par"
    CONJUNTO = "conjunto"      # universo o recorte: sector, rango de mcap…
    ESTRATEGIA = "estrategia"
    MERCADO = "mercado"        # el mercado como un todo
    SISTEMA = "sistema"        # el propio AXIOM


class Alcance(str, Enum):
    """
    Para cuántos objetos se calcula de una vez.

    No es un detalle de implementación: es el criterio de la arquitectura sobre
    qué se precalcula. Una capacidad que sirve para COMPARAR objetos entre sí se
    calcula para TODOS cuando ocurre el evento que la invalida; una que se
    consulta de a uno se calcula al pedido.

    Nadie va a rankear 3.000 pares por en qué franja hacen su máximo. Sí por
    cuánto se mueven.

    Se declara —en vez de que el motor lo infiera de la forma del resultado—
    porque el copiloto va a poder crear capacidades, y una convención implícita
    sería invisible para él.
    """
    INDIVIDUAL = "individual"   # un objeto por vez
    MASIVA = "masiva"           # todo el universo del objeto, de una


class Direccion(str, Enum):
    """
    Cómo se lee un valor más alto. Sin esto, nadie —persona o modelo— sabe si
    subir es bueno.
    """
    MAS_ES_MEJOR = "mas_es_mejor"       # rango, oscilación
    MENOS_ES_MEJOR = "menos_es_mejor"   # spread
    NEUTRA = "neutra"                   # precio: ni bueno ni malo
    CONTEXTUAL = "contextual"           # amplitud: depende de qué se busque


@dataclass(frozen=True)
class Epistemico:
    """
    Qué mide, qué infiere y qué no sabe.

    `mide` y `no_sabe` son obligatorios. `infiere` puede quedar vacío —una
    capacidad que solo lee un dato no infiere nada— pero NO SABER nada es
    imposible: toda medición tiene límites, y no declararlos es el problema que
    v3 viene a evitar.
    """
    mide: str
    no_sabe: str
    infiere: str = ""
    fuente: str = ""
    metodo: str = ""

    def __post_init__(self):
        if not self.mide.strip():
            raise ValueError("una capacidad debe declarar QUÉ MIDE")
        if not self.no_sabe.strip():
            raise ValueError(
                "una capacidad debe declarar QUÉ NO SABE. Toda medición tiene "
                "límites; no declararlos es el problema que v3 viene a evitar")


@dataclass(frozen=True)
class Propiedad:
    """
    Lo verificable de un valor: unidad, rango, cómo se lee.

    Permite que el sistema detecte un valor imposible y sepa si dos capacidades
    son comparables entre sí — cosas que con texto libre no se pueden hacer.
    """
    unidad: str = ""                       # "%", "USD", "0-1", "ratio"
    direccion: Direccion = Direccion.NEUTRA
    minimo: float | None = None
    maximo: float | None = None

    # El valor de referencia MEDIDO, no supuesto. Es el aporte más importante:
    # casi ninguno cae donde uno supondría. La amplitud del universo tiene su
    # neutro en ~42 %, no en 50 — usar 50 produce lecturas sesgadas.
    neutro: float | None = None
    neutro_medido_en: str = ""             # sobre qué período se midió

    # Si NO es comparable entre objetos. `rango_promedio` existe solo para
    # calcular un ratio: ordenar por él pone colapsos en la cabecera.
    comparable: bool = True
    por_que_no_comparable: str = ""

    def fuera_de_rango(self, v: float) -> bool:
        if v is None:
            return False
        if self.minimo is not None and v < self.minimo:
            return True
        if self.maximo is not None and v > self.maximo:
            return True
        return False


@dataclass(frozen=True)
class Vigencia:
    """
    Hasta cuándo vale un resultado.

    Se declara POR EVENTO antes que por tiempo: *"vale hasta que cierre la vela
    diaria"* es lo que realmente pasa; *"vale 6 horas"* es arbitrario. Solo lo
    que depende de datos continuos —precio, spread— usa tiempo.
    """
    evento: str = ""            # nombre del evento que la invalida
    segundos: int | None = None

    def __post_init__(self):
        if not self.evento and self.segundos is None:
            raise ValueError(
                "una capacidad debe declarar su vigencia: un evento que la "
                "invalida, o cuántos segundos vale")


@dataclass
class Capacidad:
    """Lo que el sistema sabe hacer. Base de simples y compuestas."""
    nombre: str
    objeto: Objeto
    descripcion: str
    epistemico: Epistemico
    vigencia: Vigencia
    propiedad: Propiedad = field(default_factory=Propiedad)
    parametros: dict[str, Any] = field(default_factory=dict)
    alcance: Alcance = Alcance.INDIVIDUAL

    @property
    def es_compuesta(self) -> bool:
        return False


@dataclass
class Simple(Capacidad):
    """
    Mide algo directamente: de una fuente, de una tabla, o calculando.

    `funcion` recibe el contexto y los parámetros, y devuelve el valor.
    """
    funcion: Callable[..., Awaitable[Any]] | None = None

    @property
    def es_compuesta(self) -> bool:
        return False


@dataclass
class Compuesta(Capacidad):
    """
    Combina otras capacidades mediante una operación.

    `componentes` son nombres, no objetos: así una compuesta puede declararse
    antes que sus partes y el registro resuelve al final. Y permite que la
    declaración viva en un YAML.
    """
    operacion: str = ""
    componentes: list[str] = field(default_factory=list)
    pesos: dict[str, Any] = field(default_factory=dict)

    @property
    def es_compuesta(self) -> bool:
        return True


# ══ El resultado ═════════════════════════════════════════════════════════════

@dataclass
class Resultado:
    """
    Lo que devuelve una capacidad: el valor MÁS su procedencia.

    Nunca solo el valor. Cuando el consumidor es un modelo que razona, un
    número sin su frescura ni sus límites es peligroso: lo toma como verdad y
    construye encima.
    """
    capacidad: str
    valor: Any
    calculado_at: datetime
    fuente_hasta: datetime | None = None
    vigente_hasta: datetime | None = None
    vigente_evento: str = ""
    desde_cache: bool = False

    # Lo epistémico, compuesto hacia arriba
    mide: str = ""
    infiere: str = ""
    no_sabe: list[str] = field(default_factory=list)

    # Para las compuestas: qué pasó con cada parte. Si `regimen_btc` se calculó
    # con 10 de 12 señales, eso CAMBIA la lectura y no puede quedar oculto.
    componentes: dict[str, Any] = field(default_factory=dict)
    faltantes: list[str] = field(default_factory=list)

    advertencias: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        d = {
            "capacidad": self.capacidad,
            "valor": self.valor,
            "vigencia": {
                "calculado_at": self.calculado_at.isoformat(),
                "fuente_hasta": self.fuente_hasta.isoformat() if self.fuente_hasta else None,
                "vigente_hasta": self.vigente_hasta.isoformat() if self.vigente_hasta else None,
                "vigente_evento": self.vigente_evento or None,
                "desde_cache": self.desde_cache,
            },
            "epistemico": {
                "mide": self.mide,
                "infiere": self.infiere or None,
                "no_sabe": self.no_sabe,
            },
        }
        if self.componentes:
            d["componentes"] = self.componentes
        if self.faltantes:
            d["faltantes"] = self.faltantes
        if self.advertencias:
            d["advertencias"] = self.advertencias
        return d


# ══ El registro ══════════════════════════════════════════════════════════════

class RegistroCapacidades:
    """
    Dónde viven las capacidades. Verifica al registrar, no al usar.
    """

    def __init__(self):
        self._caps: dict[str, Capacidad] = {}
        self._operaciones: dict[str, Callable] = {}

    # ── Registro ────────────────────────────────────────────────────────────
    def registrar(self, cap: Capacidad) -> Capacidad:
        if cap.nombre in self._caps:
            raise ValueError(f"capacidad duplicada: {cap.nombre}")
        if isinstance(cap, Simple) and cap.funcion is None:
            raise ValueError(f"'{cap.nombre}' es simple y no tiene función")
        if isinstance(cap, Compuesta):
            if not cap.operacion:
                raise ValueError(f"'{cap.nombre}' es compuesta y no declara operación")
            if not cap.componentes:
                raise ValueError(f"'{cap.nombre}' es compuesta y no declara componentes")
        self._caps[cap.nombre] = cap
        logger.debug("[capacidades] + %s (%s)", cap.nombre, cap.objeto.value)
        return cap

    def operacion(self, nombre: str):
        """Registra una operación. Van en código: son ocho y son estables."""
        def deco(f):
            self._operaciones[nombre] = f
            return f
        return deco

    # ── Verificación ────────────────────────────────────────────────────────
    def verificar(self) -> list[str]:
        """
        Coherencia del registro entero. Se corre AL ARRANCAR.

        Devuelve todos los problemas juntos: corregir de a uno es
        innecesariamente lento cuando ya se los vio a todos.
        """
        problemas: list[str] = []

        for nombre, cap in self._caps.items():
            if isinstance(cap, Compuesta):
                if cap.operacion not in self._operaciones:
                    problemas.append(
                        f"'{nombre}' usa la operación '{cap.operacion}', que no "
                        f"está registrada. Hay: {sorted(self._operaciones)}")
                for c in cap.componentes:
                    if c not in self._caps:
                        problemas.append(
                            f"'{nombre}' compone '{c}', que no está registrada")

                # Ciclos: A compone B que compone A colgaría el motor.
                ciclo = self._buscar_ciclo(nombre, set())
                if ciclo:
                    problemas.append(f"ciclo de composición: {' → '.join(ciclo)}")

        return problemas

    def _buscar_ciclo(self, nombre: str, visitando: set[str]) -> list[str] | None:
        if nombre in visitando:
            return [nombre]
        cap = self._caps.get(nombre)
        if not isinstance(cap, Compuesta):
            return None
        visitando = visitando | {nombre}
        for c in cap.componentes:
            if c not in self._caps:
                continue
            r = self._buscar_ciclo(c, visitando)
            if r:
                return [nombre] + r
        return None

    # ── Consulta ────────────────────────────────────────────────────────────
    def obtener(self, nombre: str) -> Capacidad:
        cap = self._caps.get(nombre)
        if cap is None:
            raise KeyError(
                f"capacidad '{nombre}' no declarada. "
                f"Hay {len(self._caps)}: {sorted(self._caps)[:10]}…")
        return cap

    def listar(self, objeto: Objeto | None = None) -> list[dict]:
        """El catálogo. Es lo que permite que un cliente descubra qué hay."""
        return [
            {
                "nombre": c.nombre,
                "objeto": c.objeto.value,
                "tipo": "compuesta" if c.es_compuesta else "simple",
                "alcance": c.alcance.value,
                "descripcion": c.descripcion,
                "operacion": getattr(c, "operacion", None),
                "componentes": getattr(c, "componentes", None),
                "parametros": c.parametros or None,
                "unidad": c.propiedad.unidad or None,
                "direccion": c.propiedad.direccion.value,
                "neutro": c.propiedad.neutro,
                "comparable": c.propiedad.comparable,
                "vigencia": (c.vigencia.evento
                             or f"{c.vigencia.segundos}s"),
                "mide": c.epistemico.mide,
                "infiere": c.epistemico.infiere or None,
                "no_sabe": c.epistemico.no_sabe,
            }
            for c in sorted(self._caps.values(), key=lambda x: x.nombre)
            if objeto is None or c.objeto == objeto
        ]

    def arbol(self, nombre: str, nivel: int = 0) -> list[str]:
        """
        De qué se compone algo, recursivamente. Es lo que permite explicar de
        dónde salió una respuesta.
        """
        cap = self.obtener(nombre)
        marca = "  " * nivel + ("├ " if nivel else "")
        lineas = [f"{marca}{nombre}"
                  + (f"  ({cap.operacion})" if cap.es_compuesta else "")]
        if isinstance(cap, Compuesta):
            for c in cap.componentes:
                if c in self._caps:
                    lineas += self.arbol(c, nivel + 1)
                else:
                    lineas.append("  " * (nivel + 1) + f"├ {c}  ← NO REGISTRADA")
        return lineas

    def __len__(self) -> int:
        return len(self._caps)

    @property
    def operaciones(self) -> list[str]:
        return sorted(self._operaciones)


registro = RegistroCapacidades()
