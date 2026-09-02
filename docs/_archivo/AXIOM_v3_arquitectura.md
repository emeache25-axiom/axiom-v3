# AXIOM v3 — Arquitectura

> Escrito el 18/08/2026, derivado del documento fundacional.
>
> **v3 no se construye sobre v2.** v2 es referencia —enseñó qué funciona y qué
> no— pero no es la base. Este documento define cómo se organiza v3.
>
> Lo que NO define: la implementación, el stack, ni el orden de construcción.

---

## 1. El principio de derivación

En v2 cada pregunta produjo una capacidad. Resultado: 18 capacidades donde
varias hacen lo mismo sobre universos distintos, y cada pregunta nueva implicaba
capacidad nueva, widget nuevo y parche.

v3 se deriva al revés: **buscar qué operaciones se repiten entre preguntas**, y
que esas sean las capacidades.

Estas tres preguntas parecen distintas:

> *¿Qué coins subieron más puestos? · ¿Qué sectores ganan peso? · ¿Qué pares
> tienen volumen inusual?*

Y son la misma operación: **tomar una serie, comparar el presente contra su
propia historia, ordenar.** Si eso es una capacidad parametrizable, las tres la
usan. Si son tres capacidades, es v2 otra vez.

**Una pregunta nueva casi siempre es una combinación nueva, no una capacidad
nueva.** Esa es la prueba de que la arquitectura funciona — y el criterio para
saber si falló: si dentro de un tiempo una pregunta nueva exige código nuevo en
vez de una composición, el diseño no cumplió.

---

## 2. El modelo: capacidades y operaciones

### 2.1 Las tres piezas

**Capacidad simple** — mide algo directamente y lo declara.
> `dominancia_btc` mide la proporción de capitalización de Bitcoin.
> `amplitud` mide el % de miembros de un conjunto en alza.
> `rango_tipico` mide la mediana del rango diario de un par.

**Operación** — la mecánica genérica de combinar capacidades. No sabe de qué:
*clasificar* recibe votos y devuelve una lectura con convicción, sin importar si
vienen de señales de Bitcoin o de propiedades de pares.

**Capacidad compuesta** — combina capacidades mediante una operación.
> `regimen_btc` = doce señales, combinadas por *clasificar*.

### 2.2 El modelo es recursivo

Una compuesta puede componer simples, compuestas, o cualquier mezcla. Sin límite
de niveles.

```
panorama_mercado                    (compuesta · reunir)
├── regimen_btc                     (compuesta · clasificar)
│   ├── dominancia_btc              (simple)
│   ├── mvrv_zscore                 (simple)
│   └── … 10 señales más            (simples)
├── regimen_pares                   (compuesta · clasificar)
│   ├── amplitud                    (simple)
│   ├── oscilacion                  (simple)
│   └── …
└── mapa_sectores                   (compuesta · agregar)
```

### 2.3 Por qué esto resuelve el problema epistémico

Fue el punto que más costó cerrar. La pregunta era: si una capacidad es una
composición, ¿cómo se compone su declaración de qué mide, qué infiere y qué no
sabe?

**No hay que inventar reglas de composición: la composición es de capacidades, y
las capacidades ya saben declararse.**

Una compuesta **hereda** los límites de sus componentes y **agrega** los propios
de su operación:

- `dominancia_btc` declara que es dato de CoinGecko, con su frescura
- `regimen_btc` hereda eso y agrega *"el régimen es una clasificación inferida;
  la convicción mide acuerdo entre señales, no probabilidad"*

**Nadie escribe el mismo límite dos veces.**

> El intento previo fue hacer que cada operación cargara con los límites del
> dato —*"solo MEXC y CoinEx"*—. Estaba mal: eso no es propiedad de la
> operación. `agregar` no sabe ni tiene por qué saber de dónde vienen los pares.

### 2.4 La capa de operaciones

Las operaciones no se invocan sueltas: hay **una capa que las gestiona** y que
sabe tres cosas que las operaciones no:

**De dónde vienen los datos** — declarado UNA VEZ. Si mañana entra un exchange
nuevo, se cambia ahí y no en veinte lugares. El límite *"solo MEXC y CoinEx"*
deja de repetirse en cada capacidad.

**Qué necesita cada operación** — *comparar contra su historia* necesita una
serie; *clasificar* necesita votos con sus umbrales. La capa provee y valida.

**Qué devuelve cada una** — y por eso puede encadenarlas: sabe que la salida de
*agregar* sirve como entrada de *comparar contra su historia*.

Eso además le da dueño al tercer tipo de límite epistémico, el que no tenía
ninguno: **el que nace del encadenamiento**. La capa es la única que ve la cadena
completa, así que es la única que puede saber que un percentil calculado sobre 61
días está alimentando una clasificación — y declararlo.

### 2.5 Las ocho operaciones

| Operación | Combina | Ejemplo |
|---|---|---|
| **Reunir** | varias capacidades, sin transformar | `panorama_mercado` |
| **Clasificar** | señales → lectura con convicción | `regimen_btc`, `regimen_pares` |
| **Agregar** | muchos objetos → pocos números | `mapa_sectores` |
| **Comparar contra su historia** | valor → su posición en la serie | percentiles, volumen relativo |
| **Filtrar y ordenar** | conjunto + criterios → subconjunto | screener |
| **Detectar discrepancia** | dos medidas que deberían coincidir | BTC vs universo, ineficiencias |
| **Proyectar condiciones** | propiedades vs. requisitos | estrategia ↔ par |
| **Simular** | declaración + historia → señales que habría dado | validar antes de activar |

Dos observaciones:

**Comparar contra su historia es la más repetida.** Toda la capa de investigación
es esto, y funciona igual para el ranking de una coin, el volumen de un par o la
amplitud del universo: la operación es idéntica, cambia qué serie recibe.

**Detectar discrepancia es la más original.** Toda la búsqueda de ineficiencias
es esto, y ninguna plataforma existente la ofrece.

> **Verificado contra todas las preguntas del fundacional.** Tres no entraban:
> *"¿qué eventos tiene por delante?"* y *"¿qué se dice de ella?"* no son
> composición sino **acceso a datos con eje temporal** (§5.3); *"¿qué habría
> pasado en 60 días?"* era un hueco real y produjo la operación **simular**.

### 2.6 Cómo se declara una compuesta

Además de lo que declara toda capacidad —nombre, descripción, qué devuelve,
bloque epistémico— una compuesta declara:

- **de qué se compone** — las capacidades que usa
- **con qué operación** — cuál de las ocho
- **con qué parámetros** — umbrales, ponderaciones, ventana

**Los parámetros van en los dos lados.** La declaración fija los valores por
defecto —lo que hace que `regimen_btc` signifique algo estable— y el pedido puede
sobrescribirlos, quedando registrado en el resultado. Es lo que v2 ya hace sin
nombrarlo: `regimen_pares` acepta `dias` y devuelve `dias_efectivos`.

**El resultado de una compuesta no es solo el valor: es el valor más el estado de
cada componente.** Si `regimen_btc` se calculó con 10 de 12 señales porque dos no
estaban disponibles, eso cambia la lectura y no puede quedar oculto. En v2 se
escribe a mano; acá sale de la estructura.

### 2.7 Lo que esto habilita

**El copiloto puede componer.** Si las capacidades declaran qué reciben y qué
devuelven, y las operaciones son conocidas, una pregunta nueva puede resolverse
combinando lo que hay. *"Compará la amplitud de layer2 contra su propia
historia"* no necesita capacidad nueva: es *agregar* con recorte, encadenado con
*comparar contra su historia*.

**El sistema puede explicar su razonamiento.** Si una respuesta viene de una
composición declarada, se puede mostrar de qué salió: *"el régimen es alcista
porque 8 de 12 señales votaron así, y estas son"*. Hoy `regimen_btc` lo hace a
mano; acá saldría de la estructura.

### 2.8 Lo que hay que cuidar

**El costo de las cadenas profundas.** Una compuesta de tres niveles ejecuta
muchas capacidades. La composición tiene que **aprovechar el caché de sus
partes**, no solo el del resultado final (§7.4).

**Las composiciones sin sentido.** Nada impide encadenar *agregar el spread de un
sector de coins*. Las operaciones tienen que declarar sobre qué objetos y
propiedades aplican — y ahí el vocabulario (§4) cumple una segunda función: no
solo nombra propiedades, también dice sobre qué objeto valen. Eso restringe las
composiciones válidas.

## 3. Los objetos

**Cosas**
- **Coin** — un activo del ecosistema
- **Par** — un mercado concreto: activo + quote + exchange
- **Estrategia** — una declaración de condiciones, y sus señales

**Recortes** *(no son cosas: son subconjuntos)*
- **Sector** — coins agrupadas
- **Universo** — el conjunto completo, de coins o de pares

La distinción importa: **un sector no tiene precio propio**, tiene el agregado
de sus coins.

Y tiene una consecuencia de diseño: si sector y universo son recortes del mismo
conjunto, **las operaciones no necesitan saber sobre cuál operan**. No hay una
capacidad "mapa de sectores" y otra "panorama del universo": hay **una agregación
con un recorte declarado**.

---

## 4. El vocabulario de propiedades

Es la moneda de cambio entre capas y la pieza que hace posible la operación 8:
si una estrategia dice *"necesito rango ≥ 5 %"*, tiene que existir una propiedad
con ese nombre, medida igual, para todos los pares.

**Lección de v2:** `volatilidad`, `rango_diario_pct` y `volatility_30d` eran tres
nombres del mismo número. Y `cambio_pct` no decía contra qué comparaba — el
copiloto inventó un referente plausible dos veces.

Cada propiedad declara: **nombre estable · qué mide · unidad · cómo se calcula ·
cómo se lee.**

**La ventana es un parámetro, no parte del nombre.** No existe
`rango_tipico_30d`: existe `rango_tipico` con su ventana declarada en el
resultado. Medido en v2: se pidieron 90 días y se usaron 61 — sin declararlo,
nadie se entera.

### 4.1 Par

| Propiedad | Qué mide | Unidad | Cómo se lee |
|---|---|---|---|
| `precio` | último precio conocido | quote | — |
| `spread` | (ask − bid) / mid | % | **menos es mejor** · real medido: 0,38-0,81 % |
| `volumen` | operado en 24 h **en ese exchange** | USD | ⚠️ no cruzar con capitalización global |
| `rango_diario` | (high − low) / low del día | % | más = más movimiento |
| `rango_tipico` | **mediana** de `rango_diario` | % | el día típico · universo ≈ 5 % |
| `rango_promedio` | media de `rango_diario` | % | ⚠️ **no comparable** — ver abajo |
| `rango_ratio` | promedio / típico | ratio | ~1 parejo · alto = evento o dato roto |
| `repetibilidad` | % de días sobre un umbral | % | **curva** (1/2/3/5/8 %), no un número |
| `oscilacion` | 1 − Efficiency Ratio, en logaritmos | 0-1 | 1 = va y vuelve · 0 = tendencia o colapso |
| `rango_neto` | `rango_tipico` − 2 × `spread` | % | **cota superior** de lo capturable |
| `metricas_hasta` | hasta qué vela llegan | fecha | sin esto, un número no dice de cuándo es |

> **`rango_promedio` queda declarado NO comparable.** Existe solo porque alimenta
> `rango_ratio`. Ordenar por él pone colapsos arriba: medido en v2, ARCIELUSDT
> tenía promedio 219,94 % contra típico 0,46 % — un par plano encabezando el
> ranking de oscilación. En v2 era el criterio por defecto del screener.

> **`rango_neto` es cota superior, no promesa.** Descuenta spread pero no
> deslizamiento. En los dos pares con libro medido, la profundidad a ±0,1 % del
> mid es **cero**: una orden de unos cientos de dólares ya mueve el precio.

### 4.2 Coin

| Propiedad | Qué mide | Cómo se lee |
|---|---|---|
| `precio` | en USD | — |
| `capitalizacion` | market cap | — |
| `volumen` | 24 h **global** | ⚠️ distinto del volumen de un par |
| `puesto` | ranking por capitalización | **casi estático: informa su VARIACIÓN** |
| `variacion` | cambio de precio | ventana móvil de la fuente, **no día contra día** |
| `sector` | supercategoría | derivada de las categorías de la fuente |
| `estado` | activa / inactiva | inactiva → **no se considera en ninguna capacidad** |

> **Las dos capas no se cruzan.** El volumen de un par sobre la capitalización
> global no es un ratio: es un artefacto. Numerador de una capa, denominador de
> otra.

### 4.3 Conjunto *(universo o recorte)*

| Propiedad | Qué mide | Neutro medido |
|---|---|---|
| `amplitud` | % de miembros en alza | **≈ 42 %**, no 50 |
| `retorno_mediano` | variación del miembro típico | ≈ −0,17 % |
| `retorno_ponderado` | ponderada por capitalización | — |
| `dispersion` | ponderado − mediano | **positivo = se movieron las grandes** |
| `participacion` | % sobre su media móvil | **≈ 31 %**, no 50 |
| `concentracion` | ponderado por volumen − mediano | ≈ +0,73 |
| `fuerza_relativa` | retorno del conjunto − retorno de BTC | ≈ −0,24 % |

> **Los neutros propios son el aporte más importante de esta tabla.** Ninguno cae
> donde uno supondría. Usar 50 o 0 produce lecturas sistemáticamente sesgadas —
> pasó con la divergencia BTC/universo, donde el umbral de 50 mezclaba
> divergencia real con la deriva bajista de base.
>
> **Salvedad:** salieron de 78 días de un período bajista. Son **medidos**, no
> constantes: hay que recalibrarlos y declararlos como recalibrables.

> **`retorno_ponderado` NO es flujo de capital.** Es variación de precio
> ponderada: un sector puede subir 10 % sin que entre un dólar. En v2 la
> descripción decía "cuánto se movió el capital" y el copiloto lo repetía. Medir
> flujo real requiere volumen por sector, que hoy no se mide.

### 4.4 Estrategia

**Qué necesita** — se expresa en el mismo vocabulario que se miden los pares:

| Requisito | Se cruza con |
|---|---|
| `rango_minimo` | `rango_tipico` |
| `oscilacion_minima` | `oscilacion` |
| `repetibilidad_minima` | `repetibilidad` |
| `spread_maximo` | `spread` |
| `volumen_minimo` | `volumen` |
| `horizonte` | **con el trader** — define si es notificable |

`horizonte` no se cruza con el par: una estrategia de horizonte "minutos" no
funciona con un humano en el medio. **Se declara antes de activar, no se
descubre operando.**

**Qué hace:** `condicion_entrada` · `stop` · `target` · `invalidacion`.

> `invalidacion` suele faltar y sin ella el registro queda incompleto: una señal
> que nunca toca stop ni target se queda abierta para siempre y contamina toda
> estadística.

**Qué produce — la señal:**

`emitida_at` · `precio_señal` · `stop` · `target` · `desenlace`
(target/stop/invalidada/abierta) · `cerrada_at` · `resultado_teorico` ·
`precio_real` · `resultado_real`

> **La diferencia entre teórico y real es la medición más valiosa del sistema.**
> Ahí aparece la fricción verdadera: el hueco entre la notificación y la
> ejecución, el deslizamiento, el precio que no se alcanzó. Ninguna plataforma
> puede medirlo porque ninguna sabe a qué precio operaste.

**Derivadas de un conjunto de señales:** `señales_emitidas` · `tasa_acierto` ·
`resultado_acumulado` · `duracion_mediana` · `frecuencia` — **todo por par**, que
es lo que permite responder en cuáles funciona.

---

## 5. Lo que no son datos de mercado

Tres categorías que las secciones consumen y las operaciones no cubren.

### 5.1 Colecciones del usuario

Watchlist, estrategias activas, alertas. **Objetos que el trader crea y
administra.** La operación es alta/baja/modificación, no análisis.

Son justamente **lo que el copiloto tiene que poder modificar**: *"agregalo a la
watchlist"*.

### 5.2 Estado de trabajo

Lo dibujado, los indicadores puestos, la temporalidad, el par en foco.
**Persiste y es del trader.**

Es lo que hace posible el modelo de interacción: sin estado de vista persistido,
el copiloto no puede saber qué se está mirando ni operar la pantalla. v2 ya tiene
la mitad —`chart_state`, `chart_indicators`, `chart_drawings`— construida para
otra cosa.

### 5.3 Eventos temporales

Noticias, desbloqueos, upgrades. **Datos con eje temporal que no son propiedades
de ningún objeto.** Su vínculo con coins es difuso.

Los desbloqueos son el caso más valioso: **eventos con fecha conocida de
antemano**, información accionable que casi nadie mira.

**No se acceden por composición.** Al verificar las ocho operaciones contra todas
las preguntas (§2.5), *"¿qué eventos tiene por delante?"* y *"¿qué se dice de
ella?"* fueron las dos que no entraban en ninguna. Necesitan su propia forma de
acceso —*qué hay entre estas fechas para este objeto*— que no es una operación
sobre propiedades.

---

## 6. Presentación

Los widgets están en **otra dimensión** que todo lo anterior. Lo demás responde
*qué sabe el sistema*; los widgets, *cómo se muestra*.

Por eso pueden aparecer en cualquier lugar sin pertenecer a ninguno: una
pantalla, un panel, una respuesta del copiloto, un dashboard.

Un widget **consume una capacidad y sabe dibujarla**:

| Operación | Widget |
|---|---|
| clasificar | tarjetas de régimen con convicción |
| comparar contra su historia | barras de percentil |
| agregar | mapa de sectores |
| detectar discrepancia | gráfico de divergencia |

**Se sostiene la decisión de v2:** declaración en el backend, render en el
frontend. Es lo que permite que cualquier cliente lea el mismo catálogo —la web
hoy, una app mañana, y el copiloto montándolos en sus respuestas.

**Lo que se agrega en v3:** los widgets declaran **qué se les puede pedir**. El
gráfico acepta par, temporalidad, indicadores; una tabla acepta orden y filtros.
Eso los convierte de "vistas que se montan" en **vistas invocables**, que es lo
que hace posible *"agregá una EMA de 21"*.

---

## 7. Cómo se calcula cada cosa

### 7.1 Qué se guarda y qué no

> **Se guarda lo que no se puede volver a pedir.**
> **Lo que la fuente devuelve on-demand se calcula al vuelo.**

Con un segundo eje: **lo que se necesita a escala y con frecuencia** se guarda
aunque sea recuperable — no por disponibilidad sino por latencia.

| Se guarda | Por qué |
|---|---|
| Foto diaria del universo de coins | la fuente **no** devuelve el ranking de hace un mes: irrecuperable |
| Velas diarias de todos los pares | recuperables, pero se usan en cada consulta sobre miles de pares |
| Señales de estrategias y sus desenlaces | son hechos propios |
| Lecturas de las señales del régimen | irrecuperables |

| NO se guarda | Por qué |
|---|---|
| Velas horarias de todo el universo | el exchange las devuelve on-demand y se consultan de a un par |
| Libro de órdenes en régimen permanente | capturado "por si acaso": 3,9 GB para 2 pares en v2 |

> **El libro se captura bajo demanda y con propósito declarado**, no como
> régimen permanente. Cuando una estrategia lo requiera, se define ahí.

### 7.2 Tres modos de cálculo

| Modo | Cuándo | Ejemplos |
|---|---|---|
| **Al vuelo** | barato o cambia constantemente | precio, spread, agregados del universo |
| **Por evento, para todo el universo** | se usa para **comparar** objetos entre sí | rango, oscilación, repetibilidad |
| **Al pedido, con caché** | caro y se consulta **de a uno** | estadísticas horarias, curva de profundidad |

El criterio que decide entre los dos últimos:

> **¿La métrica se usa para comparar objetos entre sí?**
> Sí → se calcula para todos cuando ocurre el evento.
> No → se calcula cuando se pide, y se guarda mientras valga.

Nadie va a rankear 3.000 pares por en qué franja hacen máximo. Sí por rango.

### 7.3 Los eventos

Cinco. Casi todo lo que en v2 corre por reloj cuelga de uno.

| Evento | Qué dispara |
|---|---|
| **cerró la vela diaria** | rango, oscilación, repetibilidad, ratio |
| **cerró la vela horaria** | *(sin consumidores por ahora)* |
| **llegó un refresco de coins** | snapshot diario, agregados del universo |
| **cambió el universo** | alta, baja o cambio de estado |
| **se disparó una señal** | notificación y registro |

Los cuatro primeros son *"llegaron datos nuevos"*; el quinto es *"pasó algo"* —
no invalida cálculos, produce un hecho.

> **En v2 todos los jobs son por reloj y ninguno dice por qué ese momento.** El
> sync de velas corre a las 00:30 UTC porque a esa hora hay velas nuevas: ya es
> un job por evento disfrazado de cron. Declararlo como evento tiene una ventaja
> concreta — si el evento no ocurrió, no hay nada que recalcular.

> **`cambió el universo` es el que v2 no tiene**, y produjo casi todos los
> problemas: nadie se enteraba de las bajas.

### 7.4 Vigencia y caché

**Toda respuesta viaja con su vigencia.** No es opcional cuando el consumidor es
un modelo que razona.

Cada resultado declara:

- `calculado_at` — cuándo se calculó
- `fuente_hasta` — **hasta qué dato llegan los insumos** (distinto de lo anterior)
- `vigente_hasta` o `vigente_evento` — hasta cuándo vale

> `fuente_hasta` es aparte de `calculado_at` por la lección de `metricas_hasta`:
> si se calcula a las 15:00 con velas hasta ayer, la métrica cubre **hasta
> ayer**. Eso es lo que se muestra, no la hora del cálculo.

**La vigencia se declara por evento antes que por tiempo.** "Vale hasta que
cierre la vela diaria" es lo que realmente pasa; "vale 6 horas" es arbitrario.
Solo lo que depende de datos continuos —precio, spread— usa tiempo.

**El caché es transparente.** El registro decide si sirve de caché o calcula;
quien llama no se entera. Pero **la vigencia siempre viene en la respuesta**: así
nadie tiene que saber del caché y nadie puede ignorar la frescura.

**Ante un resultado vencido:** se devuelve lo anterior marcado y se recalcula en
segundo plano —*"actualizando estadísticas"*—, con la protección de que una
misma capacidad+argumentos ya en curso no se dispara de nuevo. Diez consultas
simultáneas producen un solo cálculo.

> Mostrar el dato anterior **solo es honesto si viene declarado desde cuándo
> es**. Sin eso sería el problema que v2 tenía: datos viejos presentados como
> actuales.

---

## 8. Lo que este documento NO decide

- El stack y la implementación
- **El formato concreto de declaración** de una capacidad simple, una compuesta
  y una operación — la pieza que convierte este diseño en implementable
- El orden de construcción *(criterio ya acordado: lo que acumula historia va
  primero, porque es lo único que el tiempo no perdona)*
- Qué se migra de v2 y qué se descarta *(v2 es referencia, no base)*
- Cuántas secciones habrá
- El criterio de seguimiento del universo
- Cuándo, si alguna vez, el sistema pasa de notificar a operar

### El estado de v2

**Congelada, pero corriendo.** Sigue capturando —`coin_daily`, velas, precios,
señales del régimen— porque esa historia es irrecuperable y hoy funciona bien.
No se toca: ni parches, ni capacidades nuevas, ni widgets. Si aparece un bug, se
anota; no se arregla salvo que rompa la captura.

Queda escrito para que la decisión no se erosione sola: es fácil que *"un
arreglito más"* devuelva al lugar del que v3 vino a sacarnos.

---

## Nota de método

Todo lo declarado acá está **medido**, no supuesto. Los neutros propios, los
límites del rango neto, la profundidad cero a ±0,1 %, la distorsión del promedio
frente a la mediana: cada uno salió de una hipótesis con regla de descarte
escrita antes de mirar los datos.

Lo que v2 enseñó no es qué código conservar. Es **qué preguntas hay que hacerle a
un dato antes de confiar en él** — y esa es la disciplina que v3 hereda.
