# AXIOM v3 — Declaraciones

> Escrito el 18/08/2026, derivado de la arquitectura.
>
> Cómo se declara cada pieza del sistema. Es lo que convierte el diseño en algo
> implementable: el motor lee estas declaraciones y las ejecuta.
>
> **El formato mostrado es ilustrativo**, no una decisión de sintaxis. Lo que
> importa es QUÉ se declara, no si es YAML, JSON o filas en una tabla.

---

## 0. Qué es código y qué es dato

| Pieza | Forma | Por qué |
|---|---|---|
| **Motor y operaciones** | código | pocos y estables |
| **Fuentes** | dato | cambian cuando cambia una API |
| **Capacidades simples** | dato | son muchas y se agregan seguido |
| **Capacidades compuestas** | dato | cambiar qué señales usa un régimen no debe requerir código |
| **Widgets** | dato *(declaración)* + código *(render)* | ya funciona así en v2 |
| **Estrategias** | dato | **el copiloto las crea**: no puede escribir código |

El criterio: **si lo vas a cambiar seguido, es dato.**

> **La prueba concreta que motivó esto:** `regimen_btc` hoy usa doce señales. Que
> mañana quieras cambiar una, agregar otra o mover un umbral **no puede implicar
> tocar código**. Con la declaración como dato, es editar una tabla.

---

## 1. Fuente

De dónde vienen los datos. **Se declara una vez y la usan todas las capacidades.**

> **El problema que resuelve, medido en v2:** cinco archivos hablan con CoinGecko
> y tres lo hacen sin adaptador. El arreglo del rate limit que se aplicó a
> `coins_sync` **no protege** a `categorias_fill` ni a `coin_info_service` — cada
> uno tiene su propio manejo, peor.
>
> Y hay **dos carpetas de adaptadores**: `backend/data/` (viva) y
> `backend/exchanges/` (819 líneas, **cero importadores**).

### 1.1 Modo REST

```yaml
fuente: coingecko
  tipo: rest
  base_url: https://api.coingecko.com/api/v3

  limites:
    llamadas_por_minuto: 30
    reintentos: 4
    respeta_retry_after: true      # el header, no un fijo
    espera_base_s: 5
    timeout_s: 30

  endpoints:
    mercados:
      path: /coins/markets
      params_fijos:   { vs_currency: usd, per_page: 250 }
      params_admite:  [page, ids, order, price_change_percentage]
      pagina: true
      devuelve: coleccion            # de objetos coin

    lista_completa:
      path: /coins/list
      devuelve: coleccion
      nota: >
        Única forma de saber QUÉ EXISTE — 18.423 coins. Es la referencia de
        inventario: comparar contra esto detecta altas y bajas mucho mejor que
        deducirlas de la ausencia en un listado paginado.
```

### 1.2 Modo stream

Otra naturaleza: REST es pregunta-respuesta, un stream produce datos
permanentemente. Por eso declara cosas que el REST no.

```yaml
fuente: mexc_ws
  tipo: stream
  url: wss://wbs-api.mexc.com/ws
  codificacion: protobuf            # MEXC lo usa; CoinEx es JSON

  reconexion:
    intentos: infinito
    espera_inicial_s: 1
    espera_maxima_s: 60

  canales:
    precio:
      suscripcion: spot@public.deals.v3.api.pb@{par}
      produce: ticks de precio
      retencion: ultimo_valor        # ← obligatorio declararlo

    libro:
      suscripcion: spot@public.limit.depth.v3.api.pb@{par}@10
      produce: 10 niveles de cada lado
      retencion: bajo_demanda
      nota: >
        NO se guarda por defecto. En v2 este canal generó 3,9 GB para DOS pares
        —el 98 % de toda la base— capturando 40 veces por minuto sin propósito
        declarado. Se activa la captura cuando algo la necesita, y se declara
        para qué.
```

> **`retencion` es obligatorio en todo canal.** Un stream sin política de
> retención declarada es `ob_snapshots` otra vez. Valores: `ultimo_valor` ·
> `agregado_por_ventana` · `bajo_demanda` · `todo` *(este último exige
> justificación escrita)*.

### 1.3 Capacidades de la fuente

No todas ofrecen lo mismo. **Se declara, no se descubre fallando.**

```yaml
fuente: coinex
  ofrece: [precio, velas, libro, tickers, spread]
  no_ofrece: [funding, open_interest]
  operable: true                    # se puede operar acá
```

> Era la idea de `backend/exchanges/` en v2 —adaptadores con capacidades
> declaradas— y estaba bien. Quedó sin usar.

### 1.4 La respuesta cruda se guarda

**No se declara solo lo que se usa hoy.**

Se guarda la respuesta completa y aparte se declara el **mapeo** de los campos al
vocabulario:

```yaml
mapeo: coingecko.mercados → coin
  id                                 → id
  current_price                      → precio
  market_cap                         → capitalizacion
  market_cap_rank                    → puesto
  total_volume                       → volumen
  price_change_percentage_24h        → variacion_24h
  last_updated                       → fuente_updated_at
```

Tres razones:

1. **Un campo que hoy no se usa mañana puede hacer falta** — y si se guardó
   crudo, está disponible **incluso históricamente**. Agregar un campo es agregar
   una línea al mapeo, sin volver a pedirle nada a la fuente.
2. **Si la fuente cambia su formato, queda registrado.** Hoy si CoinGecko
   renombra un campo, el sync lo lee como `None` y nadie se entera.
3. El costo es bajo: JSON de coins, no libros de órdenes. Todo v2 sin
   `ob_snapshots` pesa 89 MB.

---

## 2. Capacidad simple

Mide algo directamente. Es la unidad atómica del sistema.

```yaml
capacidad: btc_dominance
  tipo: simple
  objeto: mercado

  origen:
    fuente: coingecko
    endpoint: global
    campo: market_cap_percentage.btc

  unidad: "%"
  vigencia:
    evento: refresco_de_coins

  epistemico:
    mide: >
      la proporción de la capitalización total del mercado cripto que
      corresponde a Bitcoin, según CoinGecko
    infiere: nada — es un dato tomado de la fuente
    no_sabe: >
      es un RATIO: no dice si el mercado crece o se contrae. Una dominancia que
      sube puede ser BTC subiendo o alts cayendo, y son cosas distintas
    fuente: CoinGecko /global
    metodo: lectura directa
```

### 2.1 Con cálculo

Cuando el valor no viene de la fuente sino que se calcula:

```yaml
capacidad: rango_tipico
  tipo: simple
  objeto: par

  origen:
    tabla: velas_diarias
    parametros:
      ventana: { default: 30, min: 7, max: 180 }

  calculo: mediana(rango_diario)

  unidad: "%"
  vigencia:
    evento: cierre_vela_diaria

  epistemico:
    mide: la mediana del rango diario (high−low)/low sobre la ventana
    infiere: nada
    no_sabe: >
      es el rango DISPONIBLE, no el capturable: no descuenta spread ni
      deslizamiento. Que un par recorra 5 % no significa que se pueda comprar
      abajo y vender arriba
    metodo: mediana, no promedio — ver la nota del vocabulario
```

> **La ventana es parámetro, no parte del nombre.** No existe `rango_tipico_30d`.
> Y el resultado **siempre declara la ventana efectivamente usada**: en v2 se
> pidieron 90 días y se usaron 61, y sin declararlo nadie se entera.

### 2.2 Los cálculos son compartidos

`mediana`, `media_movil`, `ema`, `percentil`, `desvio` se declaran **una vez** y
las usa cualquier capacidad.

> En v2 `calc_mayer_multiple` y `calc_price_vs_ma50` son ambas *"precio sobre
> una media móvil"* con distinto período, escritas por separado.

---

## 3. Operación

La mecánica genérica de combinar capacidades. **Va en código**: son ocho y son
estables.

Cada una declara qué recibe, qué devuelve, y sobre qué aplica:

```yaml
operacion: clasificar
  recibe:    lista de votos con peso
  devuelve:  { lectura, conviccion, consenso, detalle_por_voto }
  aplica_a:  cualquier objeto
  parametros:
    umbrales:      requerido
    ponderaciones: opcional
  agrega_al_epistemico:
    infiere: >
      la lectura ES una clasificación inferida. La convicción mide cuánto
      coinciden las señales entre sí, NO la probabilidad de que ocurra
    no_sabe: >
      si la lectura se va a sostener. Los umbrales son una convención de
      lectura declarada, no una propiedad del dato
```

Las ocho: **reunir · clasificar · agregar · comparar contra su historia ·
filtrar y ordenar · detectar discrepancia · proyectar condiciones · simular.**

### 3.1 Interpretación: el patrón de umbrales

Verificado sobre las 12 señales de `regimen_btc` en v2: **once son la misma
estructura** — una cascada `if v > X → régimen, etiqueta`. La única distinta es
`volume_relative`, que combina dos entradas.

Por eso la interpretación por escalones es un patrón declarable:

```yaml
interpretacion: escalones
  direccion: descendente          # más alto = peor
  escalones:
    - { sobre: 60, lectura: BAJISTA,      etiqueta: "Muy Alta" }
    - { sobre: 57, lectura: ACUMULACION,  etiqueta: "Alta" }
    - { sobre: 53, lectura: ALCISTA_A,    etiqueta: "Media" }
    - { sobre: 48, lectura: ALCISTA_B,    etiqueta: "Baja" }
    - { resto:     lectura: DISTRIBUCION, etiqueta: "Muy Baja" }
```

**Agregar la señal número trece del mismo tipo es agregar un bloque como este.
Cero código.**

---

## 4. Capacidad compuesta

Combina capacidades mediante una operación.

```yaml
capacidad: regimen_btc
  tipo: compuesta
  objeto: mercado
  operacion: clasificar

  componentes:
    - { capacidad: mvrv_zscore,      peso: { largo: 1.0, medio: 0.5 } }
    - { capacidad: mayer_multiple,   peso: { largo: 1.0, medio: 0.5 } }
    - { capacidad: btc_dominance,    peso: { medio: 1.0 } }
    - { capacidad: fear_greed,       peso: { medio: 1.0, corto: 0.5 } }
    - { capacidad: funding_btc,      peso: { corto: 1.0 } }
    # … las demás

  parametros:
    temporalidades: { default: [largo, medio, corto] }

  vigencia:
    evento: snapshot_horario

  epistemico:
    # hereda automáticamente el de cada componente
    # y el que agrega la operación `clasificar`
    no_sabe_propio: >
      NO representa al resto del mercado. Medido el 12/08/2026 sobre 59 días:
      correlación 0,88 con la amplitud del universo operable, 18,6 % de días
      divergentes, y la divergencia es ASIMÉTRICA — 11 días de BTC subiendo con
      el universo cayendo, cero al revés. Para el universo operable,
      `regimen_pares`
```

### 4.1 Qué se hereda y qué se agrega

```
regimen_btc.epistemico =
      Σ epistemico de cada componente        (los límites del DATO)
    + epistemico de la operación clasificar  (los límites del MÉTODO)
    + no_sabe_propio                         (lo específico de esta composición)
```

**Nadie escribe el mismo límite dos veces.** Que `btc_dominance` sea un ratio y
no diga si el mercado crece se declara **una sola vez**, en la señal, y viaja a
todas las composiciones que la usen.

### 4.2 Los parámetros van en los dos lados

La declaración fija los **valores por defecto** —lo que hace que `regimen_btc`
signifique algo estable— y el pedido puede sobrescribirlos, **quedando
registrado en el resultado**.

### 4.3 El resultado incluye el estado de sus componentes

No es solo el valor: es el valor **más qué pasó con cada componente**.

```yaml
resultado:
  lectura: ACUMULACION
  conviccion: 100
  consenso: "4 de 4"
  componentes:
    disponibles: 10
    esperados: 12
    faltantes: [nupl, lth_supply]     # ← no puede quedar oculto
  vigencia:
    calculado_at: 2026-08-18T21:00:00Z
    fuente_hasta: 2026-08-18T20:00:00Z
    vigente_hasta: 2026-08-18T22:00:00Z
```

> Si se calculó con 10 de 12 señales porque dos no estaban disponibles, **eso
> cambia la lectura**. En v2 se escribe a mano; acá sale de la estructura.

---

## 5. Widget

**Declaración en el backend, render en el frontend.** Es de lo mejor de v2 y se
sostiene: permite que cualquier cliente lea el mismo catálogo — la web hoy, una
app mañana, y el copiloto montándolos en sus respuestas.

```yaml
widget: regimen
  consume: regimen_btc
  grupo: Mercado
  contextos: [pantalla, panel, chat, dashboard]

  densidades:
    compacto: { hasta: 560, campos: [largo, medio, corto] }
    normal:   { hasta: 900, campos: [largo, medio, corto] }
    amplio:   { hasta: null, campos: [largo, medio, corto] }

  # ── NUEVO EN v3 ──────────────────────────────────────────────
  acepta:
    temporalidades: lista de [largo, medio, corto]
    resaltar:       una temporalidad
```

### 5.1 Vistas invocables

`acepta` es lo que v2 no tiene y v3 necesita: **qué se le puede pedir a la
vista**.

Es lo que hace posible *"agregá una EMA de 21"* estando en Gráficos. El copiloto
opera sobre lo declarado, **sin conocer el JS de cada pantalla**.

```yaml
widget: grafico_velas
  consume: velas_par
  es_espacio_de_trabajo: true      # tiene estado propio del usuario
  acepta:
    par:           identificador
    temporalidad:  [1m, 5m, 15m, 1h, 4h, 1d]
    indicadores:   lista de { tipo, periodo }
    rango:         { desde, hasta }
```

---

## 6. Estrategia

**Dato por definición: el copiloto las crea conversando.**

```yaml
estrategia: rango_simple
  creada_por: copiloto
  par: ROSEBTC

  requiere:                      # se cruza con las propiedades del par
    rango_tipico:   { min: 5 }
    oscilacion:     { min: 0.90 }
    spread:         { max: 0.5 }
  horizonte: dias                # ← se cruza con el TRADER

  entrada:     precio <= banda_inferior(20, 2)
  stop:        entrada * 0.97
  target:      banda_media(20)
  invalidacion: 5 dias sin tocar stop ni target
```

> **`horizonte` no se cruza con el par: se cruza con vos.** Una estrategia de
> horizonte `minutos` no funciona con un humano en el medio. **Se declara antes
> de activar, no se descubre operando.**

> **`invalidacion` suele faltar** y sin ella el registro queda incompleto: una
> señal que nunca toca stop ni target queda abierta para siempre y contamina
> toda estadística.

---

## 7. Lo que el motor tiene que hacer

Leer estas declaraciones y:

1. **Resolver** una capacidad — si es simple, obtener o calcular; si es
   compuesta, resolver componentes y aplicar la operación
2. **Componer el epistémico** hacia arriba, sin que nadie lo repita
3. **Gestionar la vigencia** — servir de caché lo que vale, recalcular lo
   vencido, y **devolver lo anterior marcado** mientras recalcula en segundo
   plano *(una misma capacidad+argumentos ya en curso no se dispara de nuevo)*
4. **Disparar por evento** lo que corresponde a todo el universo
5. **Validar composiciones** — que las operaciones se apliquen a objetos y
   propiedades donde tienen sentido
6. **Registrar** cada resolución: qué se pidió, qué se sirvió, de dónde

---

## 8. Lo que falta definir

- La sintaxis concreta *(YAML, JSON, tablas — es lo de menos)*
- El lenguaje de las condiciones de estrategia — `precio <= banda_inferior(20,2)`
  necesita un evaluador
- Cómo se declaran las **colecciones del usuario** y el **estado de trabajo**
- Cómo se accede a los **eventos temporales** (noticias, desbloqueos): no entran
  en las ocho operaciones
- El orden de construcción

---

## Nota de método

Estas declaraciones no salieron de imaginar qué sería elegante. Cada una
responde a algo que **falló de forma medible** en v2:

| Se declara | Porque en v2… |
|---|---|
| El rate limit en la fuente | el arreglo del 429 protegía a un solo servicio de tres |
| La respuesta cruda | un campo no mapeado hoy es irrecuperable mañana |
| `retencion` en cada canal | un stream sin propósito generó 3,9 GB para 2 pares |
| La ventana como parámetro | se pidieron 90 días, se usaron 61, y no se declaraba |
| El estado de los componentes | un régimen con 10 de 12 señales se leía igual que uno completo |
| Los umbrales como dato | cambiar una señal exigía tocar código |
| `horizonte` en la estrategia | no todas las estrategias son notificables |
