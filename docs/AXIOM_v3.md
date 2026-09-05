# AXIOM v3 — Documento único

> **Qué es esto.** El documento vivo de AXIOM v3. Reemplaza y unifica los cinco
> `.md` previos (`premisa`, `fundacional`, `arquitectura`, `declaraciones`,
> `skills_estado`), que eran de dos naturalezas distintas —diseño (16-18/08) e
> implementación (real)— y ya divergían entre sí.
>
> **Regla de este documento:** cada afirmación sobre el estado del sistema está
> **medida contra el servidor**, no supuesta, y fechada. Donde algo es diseño no
> implementado, se dice. Donde es realidad verificada, se marca ✅. Verificación
> de estado: **2026-09-02**.
>
> Si estás retomando v3 en un chat nuevo, **leé esto primero**.

---

## Índice

1. Qué es AXIOM v3 — la premisa
2. Qué tiene que poder responder *(incluye el mapa completo por capa)*
3. La arquitectura — capacidades y operaciones
4. El vocabulario de propiedades
5. Cómo se declara cada pieza
6. Estado real de implementación (verificado 2026-09-02)
7. Datos, eventos y vigencia
8. Inventario y deuda — re-medido
9. Método y principios
10. El copiloto (diseño)
11. Qué sigue

---

## 1. Qué es AXIOM v3 — la premisa

**Una plataforma de información, investigación, análisis y desarrollo sobre el
mercado cripto, con la que se conversa.** Se conversa para analizar el mercado,
diseñar estrategias y ser notificado cuando se cumplen sus condiciones.

### 1.1 Por qué v3 no es v2 mejorada

v2 se pensó como **un cockpit que muestra datos**. Después aparecieron el
copiloto y el requisito de fondo cambió sin que nadie reescribiera la premisa.

Un sistema que **muestra** datos y uno que **razona sobre** datos necesitan cosas
distintas. El primero tolera un dato viejo o ambiguo: el trader lo mira, lo
interpreta, lo descarta. El segundo lo toma como verdad y construye encima.

Por eso todos los problemas que llevaron a v3 eran del mismo tipo — **datos que
mentían en silencio**, ninguno detectado por el sistema, todos hallados
persiguiendo otra cosa: un bot v1 fallando cada 5 min durante 2 meses; un sync
perdiendo 250 coins por corrida; precios redondeados a cero; 572 coins con datos
de hasta 78 días entrando a los cálculos; métricas de pares congeladas hasta 20
días; un overflow rompiendo el sync y reportado como "executed successfully".

**El diagnóstico de fondo:** no era que el código fuera malo, sino que **nada
verificaba nada**. Y el síntoma no apuntaba a un bug sino a la premisa.

| v2 | v3 |
|---|---|
| Obtener las coins de CoinGecko | **Gestionar** un universo de activos |
| Mostrar métricas en pantallas | **Responder preguntas** y sostener las respuestas |
| Pantallas que consultan datos | Un **motor** que alimenta al copiloto y al frontend |
| El trader interpreta lo que ve | El sistema **declara** qué mide, qué infiere y qué no sabe |

### 1.2 Las cuatro capas

Lo distintivo no es tenerlas: es que **la salida de una es la entrada de la
siguiente**.

```
INFORMACIÓN     el mercado está lateral con condiciones expansivas
      ↓
INVESTIGACIÓN   el capital rota hacia layer2
      ↓
ANÁLISIS        este par oscila 8 % con spread 0,3 % y vuelve al origen
      ↓
DESARROLLO      esta estrategia se ajusta a eso — la activo
      ↓
      └────────→ y sus señales registradas vuelven al ANÁLISIS
```

Ninguna plataforma existente cierra esa cadena: TradingView analiza pero no
investiga flujo; Glassnode investiga pero no diseña estrategias; Nansen informa
movimientos pero no dice qué hacer con un par concreto. El círculo se cierra en
la cuarta capa: **una estrategia que registra sus señales genera evidencia sobre
qué funciona en qué condiciones**, y eso vuelve al análisis.

### 1.3 El copiloto es el centro

No es una sección más. Las pantallas son vistas de lo que el sistema sabe; el
copiloto es la forma principal de preguntarle. Y **lee y escribe**: en v3 una
conversación puede producir algo que persiste y opera después —analizar un par,
diseñar una estrategia conversando, activarla, recibir notificaciones—. Es una
diferencia de categoría, no de grado.

### 1.4 El sistema NO opera

**Detecta condiciones y notifica. La operación la hace el trader.** Es coherencia
con el principio de siempre —AXIOM analiza, Migue decide— y baja el riesgo un
orden de magnitud: el peor caso de una estrategia mal diseñada es una
notificación equivocada, no una operación.

**Pero registra la operación completa.** Cada señal deja constancia de entrada,
stop, target y desenlace. No es paper trading simulando operaciones ficticias:
es el registro de las señales reales que la estrategia emitió. Cuando el trader
opera, se compara el resultado teórico con el real — ahí aparece la fricción
verdadera: el hueco entre la notificación y la ejecución, el deslizamiento, el
precio que no se alcanzó.

> **Salvedad declarada:** no todas las estrategias son notificables. Las que
> dependen de reaccionar en segundos no funcionan con un humano en el medio. Eso
> se declara en el catálogo, no se descubre operando.

### 1.5 Cómo se usa — tres modalidades

No compiten: se alimentan.

| Modalidad | Cuándo | Qué pasa |
|---|---|---|
| **Preguntar** | hay una pregunta formada | el copiloto responde, con widgets si corresponden |
| **Explorar** | no hay pregunta formada, se quiere mirar | las secciones |
| **Acompañar** | se está mirando algo y surge la pregunta | se pregunta *desde* la sección, con contexto |

La tercera ata las otras dos: hace que las secciones **alimenten** al copiloto en
vez de competir con él. *"¿Cómo lo ves?"* no significa nada sin saber qué se está
mirando; con contexto, el copiloto sabe que estás en Gráficos con ROSE/BTC en
diario con tal indicador. **El contexto dice SOBRE QUÉ hablar, no CON QUÉ datos:**
el copiloto usa sus capacidades para traer lo que necesite, no queda limitado a lo
que la pantalla ya cargó.

**El copiloto opera la aplicación**, no sólo responde: navega (*"mostrame el
gráfico de ese par"*), actúa sobre los datos (*"agregalo a la watchlist"*) y opera
la vista donde estás (*"agregá una EMA de 21"* cambia lo que la sección está
haciendo en ese momento). Para eso el sistema declara sus **vistas** igual que sus
capacidades: qué existe, qué parámetros acepta. Mismo patrón que los widgets —
declarar en backend, renderizar en frontend.

**La conversación tiene foco.** *"Hablame de este par"* → *"agregalo a la
watchlist"* → *"mostrame el gráfico"*: el "lo" y el "me" refieren al mismo objeto
sin nombrarlo. Hoy no existe —cada consulta resuelve su target desde cero—; v3
necesita un **objeto en foco** que persiste hasta que cambie, y que puede venir de
lo que se mira o de lo que se viene hablando.

**La línea de confirmación** no está en si el copiloto escribe, sino en si queda
algo funcionando por su cuenta después. *Directo* (se deshace fácil: watchlist,
mostrar gráfico, poner indicador, crear alerta) → sin confirmación. *Con
confirmación* (activar una estrategia que empezará a notificar, borrar cosas con
historia).

*(Todo esto es diseño: en v3 hoy el copiloto de skills responde, pero no opera la
app ni mantiene foco persistente — ver §6.)*

---

## 2. Qué tiene que poder responder

Las preguntas definen el sistema, no al revés. Siete de referencia, y la
expectativa es que se vuelvan más profundas a medida que el sistema crezca.

| # | Pregunta | Qué exige | Estado |
|---|---|---|---|
| 1 | Las coins que más subieron/bajaron en el ranking | historia del ranking | 🟡 acumulando |
| 2 | Los pares más operados en MEXC/CoinEx | — | ✅ |
| 3 | Qué par/coin tiene mayor potencial | modelo declarado + tasa base | ❌ |
| 4 | Cómo fluye el dinero en el mercado | historia de sectores y volumen | 🟡 acumulando |
| 5 | Análisis técnico de un par | datos intradía | 🟡 parcial |
| 6 | Info de una coin (ej. desbloqueos) | fuente nueva | ❌ |
| 7 | Qué estrategia se ajusta a este par | catálogo declarativo | ❌ |

Lo que revelan: faltan cuatro cosas distintas —**historia** (1, 4: sólo la da el
tiempo), **datos no capturados** (5, 6), **modelos declarados** (3, 7) y
**composición** (varias exigen combinar capacidades que hoy no se hablan)—. Y
ninguna es una pantalla: todas son preguntas a un sistema que sabe cosas.

> **El riesgo de la pregunta 3:** "potencial de subida" es una predicción. Se
> responde honestamente reformulándola —qué pares están en condiciones
> históricamente asociadas a movimientos al alza, con la tasa base medida—. Si la
> respuesta es un ranking de "estas van a subir", el sistema dejó de analizar y
> empezó a pronosticar.

### 2.1 El mapa completo, por capa — estado v3 (verificado 04/09)

El fundacional (16/08) desglosó ~50 preguntas por las cuatro capas. Aquel mapa
describía en buena parte lo que **v2** respondía. Abajo el mismo mapa con los
estados **corregidos a lo que v3 responde hoy**, medido contra el server: v3 tiene
6 módulos de dominio (`btc_intradia`, `mercado`, `par`, `posicionamiento`, `coin`,
`estado_mercado`), 17 capacidades y una operación (`reunir`). Varias capacidades
de sector/noticias/on-chain de v2 aún **no se portaron**.

Marcas: ✅ v3 hoy · 🟡 el dato existe, falta exponerlo · ⏳ falta historia (sólo
tiempo) · ❌ falta fuente, capacidad o modelo · **(v2)** existía en v2, no portado
a v3.

**INFORMACIÓN** — *el estado de las cosas, sin interpretación*

*Estado del mercado* — *el estado en grande. Funde lo que el diseño llamaba
"Estado general" y "Contexto macro": se solapaban (la dominancia es de ambas, y
`btc_estado` reúne señales de las dos), así que se organiza por OBJETO y por TIPO
DE SEÑAL, que es la distinción que sí se sostiene.*

| Pregunta | v2 (16/08) | v3 (04/09) |
|---|---|---|
| **BTC** — comportamiento (precio) | ✅ | ✅ **`btc_perfil`** (5 dimensiones, sin etiqueta) |
| **BTC** — presión en derivados (funding) | 🟡 | ✅ **`btc_funding`** |
| **BTC** — posicionamiento en opciones | ❌ | ✅ **`btc_opciones`** (put/call + max-pain) |
| **BTC** — lectura reunida ("¿cómo está BTC?") | ✅ régimen | ✅ **`btc_estado`** (reúne los 4, sin etiqueta) |
| **Mercado** — reparto de capital (dominancia) | 🟡 | ✅ **`mercado_dominancia`** |
| **Mercado** — sentimiento | 🟡 | ❌ fuente nueva |
| **Mercado** — on-chain | 🟡 | ❌ fuente nueva (la de v2 era frágil) |
| **Mercado** — cripto vs. tradicionales | ❌ | ❌ fuente nueva |
| **Universo** — ecosistema / ¿cambió vs. ayer? | ⏳ | ⏳ historia acumulando |
| **Universo** — régimen del universo operable | ✅ | ❌ necesita propiedades de conjunto (v2) |
| **Universo** — capital por sector | ✅ | ❌ falta `sector` poblado + operación agregar |

*Coins* — *sobre una coin concreta*

| Pregunta | v2 | v3 |
|---|---|---|
| estado actual (precio, cap, puesto, variaciones) | ✅ | ✅ **`coin_estado`** |
| ¿Cómo viene precio/volumen/ranking? | ✅ | ✅ **`coin_historia`** (historia corta: desde ~13/08) |
| ¿Dónde se opera y en qué mercados? | ✅ | ✅ **`coin_mercados`** (MEXC/CoinEx por `coin_id`) |
| ¿Qué es, qué hace, qué supply? | ✅ | ❌ `sector`/`categorias` vacíos, sin supply capturado |
| ¿Qué eventos tiene por delante (desbloqueos)? | ❌ | ❌ sin captura |

*Noticias*

| Pregunta | v2 | v3 |
|---|---|---|
| ¿Qué pasó hoy? / ¿qué se dice de esta coin? | ✅ | ❌ sin captura de noticias (v2) |

> **Decisión (04/09): no hay "régimen" en v3.** El diseño de v2 tenía un régimen
> que clasificaba señales (MVRV, Mayer, dominancia, fear&greed, funding) en una
> etiqueta por temporalidad. En v3 se descartó, por dos razones medidas: (1) de
> esas ~13 señales sólo existen hoy funding y dominancia —las on-chain venían de
> endpoints no oficiales de CoinMarketCap, frágiles por diseño—; (2) `btc_perfil`
> ya decidió deliberadamente NO colapsar en etiqueta, porque "alcista/bajista"
> destruye lo que distingue un mercado que sube tranquilo de uno violento. Un
> régimen contradiría esa decisión. En su lugar, **`btc_estado`** reúne las
> cuatro lecturas que sí se miden (perfil, funding, opciones, dominancia) sin
> colapsarlas: el que lee decide qué pesa.

**INVESTIGACIÓN** — *dónde hay algo, no cómo está X. Casi toda depende de comparar
contra el pasado — la capa que más sufre la falta de historia.*

| Pregunta | v2 | v3 |
|---|---|---|
| ¿Hacia dónde se mueve el dinero? / sectores que ganan peso | ⏳ | ⏳ + falta capacidad de sectores |
| ¿El movimiento es de muchas o de pocas grandes? | ✅ | ❌ (v2 — `dispersion`, no portada) |
| ¿Entra dinero nuevo o rota el que ya está? | ❌ | ❌ requiere volumen por sector |
| ¿Qué coins subieron/bajaron puestos? / entró-salió del top | ⏳ | ⏳ |
| ¿Qué pares se operan más de lo habitual? | ✅ | 🟡 dato en `pares`, sin la operación comparar-historia |
| ¿Dónde apareció volumen nuevo? | ⏳ | ⏳ |
| Ineficiencias — spread desalineado / libro fino | 🟡 | ❌ (v2) |
| Ineficiencias — desajuste mismo activo entre exchanges | ✅ | ❌ (v2 — la operación *discrepancia* no existe) |
| Ineficiencias — más rango neto por unidad de fricción | ✅ | 🟡 `rango_neto` es dato de par v2, sin capacidad en v3 |
| Candidatos — pares para operar rangos | ✅ | 🟡 con `oscilacion`/`rango_tipico`, falta filtrar-ordenar |

**ANÁLISIS** — *sobre un objeto concreto; interpretación siempre declarada*

| Pregunta | v2 | v3 |
|---|---|---|
| ¿Qué régimen describe el par? (tendencia/rango/colapso) | ✅ | 🟡 `oscilacion` lo insinúa, sin la operación clasificar |
| ¿Cuánto se mueve y con qué repetibilidad? | ✅ | ✅ **`rango_tipico` + `repetibilidad`** |
| ¿Es capturable o se lo come la fricción? | ✅ | 🟡 `rango_neto` (v2), no portado como capacidad |
| ¿Cómo se comporta su libro? ¿Aguanta tamaño? | 🟡 | ❌ libro no capturado en v3 (decisión: bajo demanda) |
| ¿Qué tan estable es en el tiempo? | ⏳ | ⏳ |
| **Comportamiento del par (frecuencias medidas)** — franja del máx/mín del día | ❌ | ❌ requiere velas horarias por par |
| ¿Cuántos días el precio vuelve al punto de partida? | ✅ | ✅ vía `oscilacion` |
| ¿Días de la semana distintos? | ⏳ | ⏳ |
| ¿Cuánto tarda en recorrer su rango típico? | ❌ | ❌ |
| AT — soportes/resistencias, niveles de reacción | ❌ | ❌ |
| ¿Dónde está respecto de su rango reciente? | ✅ | ✅ (par) / `btc_posicion` (BTC) |
| Comparación — vs. otros pares / su sector / BTC | ✅ | 🟡 capacidades masivas comparables, falta la vista |
| Aprovechamiento — ¿qué estrategia se ajusta? / tamaño | ❌ / 🟡 | ❌ |

> **"Comportamiento del par" es tu hipótesis central del rango diario.** Son
> **frecuencias medidas**, no lecturas: *"el 68 % de los días el mínimo ocurre
> antes del mediodía UTC"* se verifica contra su tasa base y dice cuándo mirar.
> Necesita **velas horarias por par** (no ticks) — un salto de granularidad
> barato. Hoy sólo hay horarias de BTC (`btc_vela_horaria`), no del universo de
> pares. Es el dato que falta para el frente de investigación de §11.

**DESARROLLO** — *donde el copiloto escribe. Todo ❌ en v2 y en v3: es la capa no
construida.*

| Bloque | Preguntas | Estado |
|---|---|---|
| Diseñar | qué estrategia se ajusta, condiciones de entrada, stop/target, viabilidad | ❌ |
| Validar | qué habría pasado en 60 días, cuántas señales, si es notificable | ❌ (necesita la operación *simular*) |
| Activar/operar | vigilar un par, notificar, registrar entrada/stop/target/desenlace | ❌ (notificar: 🟡) |
| Evaluar | cuántas funcionaron, teórico vs. real, en qué pares funciona, si se degradó | ❌ |

> **La pregunta que ninguna otra plataforma puede responder:** *"¿qué estrategia
> funciona en pares con estas características?"* — no por teoría, sino por las
> propias señales medidas. Es el cierre del círculo (capa 4 → análisis), y es todo
> lo que falta construir.

**Lectura del mapa:** v3 responde hoy, real y bien, la **caracterización de BTC**
(9 capacidades) y el **comportamiento estadístico de pares** (rango, oscilación,
repetibilidad) más el **funding**. Todo lo de coins, sectores, noticias, régimen,
investigación de flujo y desarrollo es diseño no portado o no construido. No es
regresión: v3 se rehízo de cero con disciplina, y va incorporando por capa.

---

## 3. La arquitectura — capacidades y operaciones

### 3.1 El principio de derivación


En v2 cada pregunta produjo una capacidad. v3 se deriva al revés: **buscar qué
operaciones se repiten entre preguntas**, y que esas sean las capacidades.

> *¿Qué coins subieron más puestos? · ¿Qué sectores ganan peso? · ¿Qué pares
> tienen volumen inusual?* — son la misma operación: **tomar una serie, comparar
> el presente contra su propia historia, ordenar.**

**Una pregunta nueva casi siempre es una combinación nueva, no una capacidad
nueva.** Ese es el criterio de éxito de la arquitectura — y el de fracaso: si una
pregunta nueva exige código nuevo en vez de una composición, el diseño no
cumplió.

### 3.2 Las tres piezas

- **Capacidad simple** — mide algo directamente y lo declara. (`rango_tipico`
  mide la mediana del rango diario de un par.)
- **Operación** — la mecánica genérica de combinar capacidades. No sabe de qué:
  *clasificar* recibe votos y devuelve una lectura con convicción, vengan de
  señales de BTC o de propiedades de pares.
- **Capacidad compuesta** — combina capacidades mediante una operación.
  (`btc_perfil` = cinco dimensiones combinadas por *reunir*.)

El modelo es **recursivo**: una compuesta puede componer simples, compuestas, o
cualquier mezcla, sin límite de niveles (el motor pone un tope de 8 para atrapar
ciclos).

### 3.3 Las ocho operaciones (diseño)

| Operación | Combina | Ejemplo | Impl. |
|---|---|---|---|
| **Reunir** | varias capacidades, sin transformar | `btc_perfil` | ✅ |
| **Clasificar** | señales → lectura con convicción | `regimen_btc` | ❌ |
| **Agregar** | muchos objetos → pocos números | `mapa_sectores` | ❌ |
| **Comparar contra su historia** | valor → su posición en la serie | percentiles | 🟡¹ |
| **Filtrar y ordenar** | conjunto + criterios → subconjunto | screener | ❌ |
| **Detectar discrepancia** | dos medidas que deberían coincidir | BTC vs universo | ❌ |
| **Proyectar condiciones** | propiedades vs. requisitos | estrategia ↔ par | ❌ |
| **Simular** | declaración + historia → señales | validar antes de activar | ❌ |

¹ *No existe como operación componible, pero varias capacidades simples ya
calculan su percentil histórico internamente (todas las `btc_*` traen percentil).
La operación genérica que lo haga sobre cualquier serie está pendiente.*

**Dos observaciones del diseño:** *comparar contra su historia* es la más
repetida (toda la capa de investigación es esto); *detectar discrepancia* es la
más original (toda la búsqueda de ineficiencias, y ninguna plataforma la ofrece).

### 3.4 Por qué esto resuelve el problema epistémico

Fue el punto que más costó cerrar: si una capacidad es una composición, ¿cómo se
compone su declaración de qué mide, infiere y no sabe?

**No hay que inventar reglas: la composición es de capacidades, y las capacidades
ya saben declararse.** Una compuesta **hereda** los límites de sus componentes y
**agrega** los de su operación. Nadie escribe el mismo límite dos veces.

```
compuesta.epistemico =
      Σ epistemico de cada componente        (los límites del DATO)
    + epistemico de la operación             (los límites del MÉTODO)
    + no_sabe_propio                         (lo específico de esta composición)
```

Esto **está implementado y verificado**: el motor (`backend/nucleo/motor.py`)
compone lo epistémico hacia arriba y registra el estado de cada componente
(cuántas señales de cuántas se usaron) desde la estructura, no a mano.

### 3.5 Los objetos y los recortes

**Cosas:**
- **Coin** — un activo del ecosistema (universo CoinGecko).
- **Par** — un mercado concreto: activo + quote + exchange (operable en MEXC /
  CoinEx).
- **Mercado** — el agregado / BTC como referencia.
- **Estrategia** — una declaración de condiciones, y sus señales.

**Recortes** *(no son cosas: son subconjuntos)*:
- **Sector** — coins agrupadas. **No tiene precio propio**, tiene el agregado de
  sus coins.
- **Universo** — el conjunto completo, de coins o de pares.

Que sector y universo sean recortes del mismo conjunto tiene una consecuencia:
**las operaciones no necesitan saber sobre cuál operan.** No hay una capacidad
"mapa de sectores" y otra "panorama del universo": hay **una agregación con un
recorte declarado**.

El vocabulario cumple una segunda función: además de nombrar propiedades, dice
**sobre qué objeto valen**. Eso restringe las composiciones válidas —nada de
"agregar el spread de un sector de coins"— y es lo que un motor de validación
usa para rechazar composiciones sin sentido.

---

## 4. El vocabulario de propiedades

Es la moneda de cambio entre capas y lo que hace posible cruzar una estrategia
con un par: si la estrategia dice *"necesito rango ≥ 5 %"*, tiene que existir una
propiedad con ese nombre, medida igual, para todos los pares.

> **Lección de v2:** `volatilidad`, `rango_diario_pct` y `volatility_30d` eran
> tres nombres del mismo número. Y `cambio_pct` no decía contra qué comparaba — el
> copiloto inventó un referente plausible dos veces. Cada propiedad declara:
> **nombre estable · qué mide · unidad · cómo se calcula · cómo se lee.**

> **Nota de estado (02/09).** Las tablas de abajo son el **vocabulario de diseño**
> (arquitectura, 18/08). En v3 hoy están implementadas como capacidad sólo
> `rango_tipico`, `oscilacion` y `repetibilidad` (objeto par) y las cinco
> dimensiones + derivadas de BTC (objeto mercado). El resto —spread, rango_neto,
> las propiedades de coin y las de conjunto— son **diseño medido en v2, no
> portado a v3 como capacidad**. Los neutros son datos empíricos reales (medidos
> sobre 78 días de un período bajista) y **recalibrables**, no constantes.

### 4.1 Propiedades del par

| Propiedad | Qué mide | Unidad | Cómo se lee | v3 |
|---|---|---|---|---|
| `precio` | último precio conocido | quote | — | 🟡 |
| `spread` | (ask − bid) / mid | % | **menos es mejor** · real: 0,38-0,81 % | ❌ |
| `volumen` | operado en 24 h en ese exchange | USD | ⚠️ no cruzar con capitalización global | 🟡 |
| `rango_diario` | (high − low) / low del día | % | más = más movimiento | ✅ (insumo) |
| `rango_tipico` | **mediana** de `rango_diario` | % | el día típico · universo ≈ 5 % | ✅ |
| `rango_promedio` | media de `rango_diario` | % | ⚠️ **no comparable** | ❌ |
| `rango_ratio` | promedio / típico | ratio | ~1 parejo · alto = evento o dato roto | ❌ |
| `repetibilidad` | % de días sobre un umbral | % | **curva** (1/2/3/5/8 %), no un número | ✅ |
| `oscilacion` | 1 − Efficiency Ratio, en logaritmos | 0-1 | 1 = va y vuelve · 0 = tendencia/colapso | ✅ |
| `rango_neto` | `rango_tipico` − 2 × `spread` | % | **cota superior** de lo capturable | ❌ |
| `metricas_hasta` | hasta qué vela llegan | fecha | sin esto un número no dice de cuándo es | ✅ (`fuente_hasta`) |

> **`rango_promedio` queda declarado NO comparable.** Existe sólo para alimentar
> `rango_ratio`. Ordenar por él pone colapsos arriba: en v2, ARCIELUSDT tenía
> promedio 219,94 % contra típico 0,46 % — un par plano encabezando el ranking de
> oscilación, y era el criterio por defecto del screener de v2.

> **`rango_neto` es cota superior, no promesa.** Descuenta spread pero no
> deslizamiento. En los dos pares con libro medido, la profundidad a ±0,1 % del
> mid es **cero**: una orden de unos cientos de dólares ya mueve el precio.

### 4.2 Propiedades de la coin

*(Ninguna implementada como capacidad en v3 — no hay módulo de coin. El dato vive
en `coin_diaria` / `coins`.)*

| Propiedad | Qué mide | Cómo se lee |
|---|---|---|
| `precio` | en USD | — |
| `capitalizacion` | market cap | — |
| `volumen` | 24 h **global** | ⚠️ distinto del volumen de un par |
| `puesto` | ranking por capitalización | **casi estático: informa su VARIACIÓN** |
| `variacion` | cambio de precio | ventana móvil de la fuente, no día contra día |
| `sector` | supercategoría | derivada de las categorías de la fuente |
| `estado` | activa / inactiva | inactiva → **no se considera en ninguna capacidad** |

> **Las dos capas no se cruzan.** El volumen de un par sobre la capitalización
> global no es un ratio: es un artefacto. Numerador de una capa, denominador de
> otra.

### 4.3 Propiedades de conjunto *(universo o recorte)*

*(Ninguna implementada como capacidad en v3. Los neutros son el aporte más
valioso de esta tabla — ninguno cae donde uno supondría.)*

| Propiedad | Qué mide | Neutro medido (v2) |
|---|---|---|
| `amplitud` | % de miembros en alza | **≈ 42 %**, no 50 |
| `retorno_mediano` | variación del miembro típico | ≈ −0,17 % |
| `retorno_ponderado` | ponderada por capitalización | — |
| `dispersion` | ponderado − mediano | **positivo = se movieron las grandes** |
| `participacion` | % sobre su media móvil | **≈ 31 %**, no 50 |
| `concentracion` | ponderado por volumen − mediano | ≈ +0,73 |
| `fuerza_relativa` | retorno del conjunto − retorno de BTC | ≈ −0,24 % |

> **Los neutros propios son el aporte más importante de esta tabla.** Usar 50 o 0
> produce lecturas sistemáticamente sesgadas — pasó con la divergencia
> BTC/universo, donde el umbral de 50 mezclaba divergencia real con la deriva
> bajista de base. **Salvedad:** salieron de 78 días de un período bajista. Son
> medidos, no constantes: hay que recalibrarlos y declararlos como recalibrables.

> **`retorno_ponderado` NO es flujo de capital.** Es variación de precio
> ponderada: un sector puede subir 10 % sin que entre un dólar. En v2 la
> descripción decía "cuánto se movió el capital" y el copiloto lo repetía. Medir
> flujo real requiere volumen por sector, que hoy no se mide.

### 4.4 Propiedades de la estrategia

**Qué necesita** — en el mismo vocabulario con que se miden los pares, para
cruzarse:

| Requisito | Se cruza con |
|---|---|
| `rango_minimo` | `rango_tipico` |
| `oscilacion_minima` | `oscilacion` |
| `repetibilidad_minima` | `repetibilidad` |
| `spread_maximo` | `spread` |
| `volumen_minimo` | `volumen` |
| `horizonte` | **con el trader** — define si es notificable |

**Qué hace:** `condicion_entrada` · `stop` · `target` · `invalidacion`.
**Qué produce (la señal):** `emitida_at` · `precio_señal` · `stop` · `target` ·
`desenlace` (target/stop/invalidada/abierta) · `cerrada_at` · `resultado_teorico`
· `precio_real` · `resultado_real`.
**Derivadas de un conjunto de señales:** `señales_emitidas` · `tasa_acierto` ·
`resultado_acumulado` · `duracion_mediana` · `frecuencia` — **todo por par**.

> **La diferencia entre teórico y real es la medición más valiosa del sistema.**
> Ninguna plataforma puede medirla porque ninguna sabe a qué precio operaste.
> Y **`invalidacion` suele faltar**: sin ella una señal que nunca toca stop ni
> target queda abierta para siempre y contamina toda estadística.

*(Todo este vocabulario de estrategia es diseño: en v3 no hay estrategias aún.)*

---

## 5. Cómo se declara cada pieza

> El diseño original (`declaraciones.md`) mostraba formato YAML, marcándolo como
> ilustrativo. **La implementación real declara en Python** vía
> `registro.registrar(Simple(...))` / `registro.registrar(Compuesta(...))` en los
> módulos de `backend/dominio/`, llamados desde `declarar()` de cada módulo. Lo
> que sigue describe QUÉ se declara; la forma es el objeto Python.

### 5.1 Qué es código y qué es dato

| Pieza | Forma | Por qué |
|---|---|---|
| Motor y operaciones | código | pocos y estables |
| Fuentes | dato | cambian cuando cambia una API |
| Capacidades simples | dato/decl. | son muchas y se agregan seguido |
| Capacidades compuestas | dato/decl. | cambiar qué señales usa un régimen no debe requerir código |
| Widgets | dato (decl.) + código (render) | ya funcionaba así en v2 |
| Estrategias | dato | **el copiloto las crea**: no puede escribir código |

El criterio: **si lo vas a cambiar seguido, es dato.**

### 5.2 Una capacidad simple declara

- **nombre, objeto** (mercado/par/coin), **tipo** (simple), **alcance**
  (individual/masiva)
- **origen** — fuente+endpoint, o tabla+cálculo
- **parámetros** — con default/min/max; **la ventana es parámetro, no parte del
  nombre** (no existe `rango_tipico_30d`), y el resultado declara la ventana
  efectivamente usada
- **propiedad** — unidad, dirección, neutro, min/max, si es comparable
- **vigencia** — el evento que la invalida
- **epistémico** — `mide` (obligatorio), `no_sabe` (obligatorio), `infiere`
  (opcional), `fuente`, `metodo`

El bloque epistémico es obligatorio por construcción: el registro rechaza al
arrancar una capacidad sin `mide` o sin `no_sabe`. *No declarar los límites es el
problema que v3 vino a evitar.*

### 5.3 Una capacidad compuesta declara además

- **de qué se compone** (nombres de capacidades), **con qué operación**, **con
  qué parámetros** (defaults que el pedido puede sobrescribir, quedando
  registrados)
- **el resultado incluye el estado de sus componentes**: si se calculó con 10 de
  12 señales, eso cambia la lectura y no puede quedar oculto — sale de la
  estructura.

### 5.4 Data-para-razonar y data-para-mostrar viajan separadas

Cada capacidad declara su `destila` (campos destinados al razonamiento, que ve el
LLM) y su `presentacion` (campos para el widget del frontend, que **nunca** se
mandan al LLM). Es lo que evita que el modelo consuma datasets crudos que no debe
procesar (ver §6.2).

### 5.5 La declaración de fuentes

De dónde vienen los datos **se declara una vez y la usan todas las capacidades**.
Resuelve un problema medido en v2: cinco archivos hablaban con CoinGecko, tres sin
adaptador; el arreglo de rate limit de un servicio no protegía a los otros. Y
había dos carpetas de adaptadores, una de ellas (`backend/exchanges/`, 819 líneas)
sin un solo importador.

Una fuente declara su **modo** (REST es pregunta-respuesta; stream produce datos
permanentemente), sus **límites** (llamadas/min, reintentos, respeta
`retry-after`), sus **endpoints** o **canales**, y qué **ofrece / no ofrece** (se
declara, no se descubre fallando: CoinEx `no_ofrece: [funding, open_interest]`).

> **`retencion` es obligatorio en todo canal de stream.** Un stream sin política
> de retención declarada es `ob_snapshots` otra vez —el canal de libro que en v2
> generó 3,9 GB para 2 pares capturando 40 veces por minuto sin propósito—.
> Valores: `ultimo_valor` · `agregado_por_ventana` · `bajo_demanda` · `todo`
> (este último exige justificación escrita).

**La respuesta cruda se guarda, y aparte se declara el mapeo** de sus campos al
vocabulario. Tres razones: un campo que hoy no se usa mañana puede hacer falta —y
si se guardó crudo está disponible incluso históricamente—; si la fuente cambia su
formato, queda registrado en vez de leerse como `None` en silencio; y el costo es
bajo (JSON de coins, no libros: todo v2 sin `ob_snapshots` pesa 89 MB).

### 5.6 El patrón de umbrales (para *clasificar*)

Verificado sobre las 12 señales de `regimen_btc` en v2: **once son la misma
estructura** —una cascada `if v > X → régimen, etiqueta`—. Por eso la
interpretación por escalones es declarable como dato (dirección + lista de
`{sobre: N, lectura, etiqueta}`), y **agregar la señal trece del mismo tipo es
agregar un bloque, cero código.** *(Aplica cuando exista la operación `clasificar`
—hoy no está en v3.)*

---

## 6. Estado real de implementación (verificado 2026-09-02)

Esta es la sección que a los cuatro documentos de diseño les faltaba: **qué está
construido y corriendo, medido contra el server.**

### 6.1 Infraestructura

- Servidor personal **`decentralia`** (192.168.0.88), Debian. Python por pyenv,
  venv en `/home/migue/apps/axiom-v3/`. PostgreSQL 17.
- **v3 corre en el puerto 8003**, servicio systemd **`axiom-v3.service`**.
- **v2 quedó congelada en 8002** (`axiom-v2.service`), corriendo sólo para
  preservar su historia. No se toca.
- Repo: `github.com/emeache25-axiom/axiom-v3`. Deploy por **parches y archivos
  que cambian** (no paquetes completos, para no pisar correcciones locales); scp
  desde `C:\Users\Migueh\Downloads`.

**Fuentes integradas (captura, 02/09):** CoinGecko (`universo` — coins), MEXC +
CoinEx (`pares` — operables), Binance (`bitcoin` — velas y series de BTC),
Deribit (`funding` + `opciones`), CoinGecko `/global` (dominancia). **Sin integrar:** noticias, desbloqueos/eventos
temporales, on-chain, sentimiento, mercados tradicionales.

**Módulos de dominio vivos (6):** `btc_intradia`, `mercado`, `par`,
`posicionamiento`, `coin`, `estado_mercado`. No hay módulo de coin, sector, universo-como-capacidad,
noticias ni estrategias. **Routers montados (3):** `capacidades`, `sistema`,
`configuracion` — la app expone el motor de capacidades, no endpoints de
coin/par/noticia/watchlist.

### 6.2 El giro de AGENTES a SKILLS

Durante varias sesiones se construyó un enfoque **multi-agente** (cinco agentes,
cada uno un LLM con tool-calling en loop). **Se abandonó — falló
estructuralmente, medido:** el loop hacía que el LLM recibiera los resultados
crudos de las capacidades en su contexto; `top_coins` devuelve ~89.000 tokens,
excediendo el límite de TPM del free tier. Fallaba ~10 de 11 veces, 45-94s.

**La decisión (de Migue): no necesitamos agentes, necesitamos skills.** Las
capacidades del registro **ya son** las skills; los agentes eran andamiaje. En
producción el **código orquesta y el LLM es sólo un nodo que entiende y
redacta**, no un cerebro autónomo tragando datos en loops.

**El copiloto de skills** (`/api/experimental/copiloto-skills`): cuatro etapas
orquestadas por código — clasificar intención por regex (sin LLM), resolver la
coin desde la DB, ejecutar y destilar skills en paralelo (Python puro), redactar
con **una sola** llamada al LLM. ~5 segundos, una llamada, cero errores de
contexto. LLM en producción: **Gemini Flash**.

> **Decisión firme del fundacional:** el copiloto de skills es la evolución de
> Kepler, no su complemento. No conviven. **Verificado 02/09:** `chat.py`
> (function calling), el orquestador multi-agente y `chat_groq` **no existen en
> v3** —no hay archivo ni router montado en `app.py`/`rutas.py`—. No fue una
> limpieza ejecutada: nunca se portaron desde v2.

### 6.3 Las 17 capacidades declaradas

Fuente autoritativa: `GET /api/capacidades` → **total: 17** (04/09). Una sola
operación implementada: **`reunir`**.

**Mercado / BTC-referencia (11):**

| Capacidad | Tipo | Mide (resumen) |
|---|---|---|
| `btc_direccion` | simple | retorno acumulado de la ventana + percentil histórico |
| `btc_volatilidad` | simple | desvío de retornos log diarios, anualizado + percentil |
| `btc_estructura` | simple | 1−(desplazamiento neto/recorrido total) + percentil |
| `btc_posicion` | simple | distancia % al máximo histórico + percentil |
| `btc_participacion` | simple | volumen medio ventana / ventana 5× + percentil |
| `btc_perfil` | **compuesta** (`reunir`) | las 5 dimensiones juntas, sin etiqueta |
| `btc_recorrido_oculto` | simple | mediana(recorrido intradía / rango de la vela) |
| `btc_funding` | simple | tasa de funding actual (fracción), percentil, signo |
| `btc_opciones` | simple | put/call + OI (contexto) y max-pain de corto plazo |
| `mercado_dominancia` | simple | dominancia BTC/ETH, cap y volumen totales, cambio |
| `btc_estado` | **compuesta** (`reunir`) | perfil + funding + opciones + dominancia, sin etiqueta |

**Par (3):** `oscilacion`, `rango_tipico`, `repetibilidad` — las tres **masivas**
(todo el universo de pares por evento). Son "la mitad medida" de la ecuación de
estrategias (§11): describen el comportamiento del par que un catálogo de
estrategias cruzaría con sus requisitos.

**Coin (3):** `coin_estado`, `coin_historia`, `coin_mercados` — INDIVIDUAL,
consulta al pedido (ver §6.6). Primeras capacidades sobre un objeto con id que no
es BTC.

Las cinco dimensiones de BTC son **independientes por diseño** (correlaciones
bajas a 30 días); `btc_perfil` deliberadamente **no colapsa en una etiqueta**
—"alcista"/"bajista" destruiría lo que distingue un mercado que sube tranquilo de
uno que sube violento—. `btc_estado` extiende esa misma disciplina a cuatro
lecturas (comportamiento, funding, opciones, dominancia): reúne, no clasifica.

> **Hallazgo (02/09): v3 tiene un solo evento de vigencia implementado,**
> `cierre_vela_diaria`, y desde el 04/09 también **`refresco_de_coins`** (usado
> por `mercado_dominancia` y las capacidades de coin deberían migrar a él). El
> planificador corre 5 jobs (§6.5) y el diseño nombra 5 eventos (§7.2), pero como
> *eventos de invalidación de caché* recién ahora hay dos vivos. `cambio_universo`
> sigue en el diseño, sin implementar.

### 6.4 Posicionamiento (Deribit) — construido esta sesión

`backend/dominio/posicionamiento.py`, enganchado en `backend/app.py`. Dos
capacidades INDIVIDUAL sobre `mercado`, vigencia `cierre_vela_diaria`. Son de
**BTC-referencia**, no de un par operable.

- **`btc_funding`** — lee `funding_btc` (Deribit perpetuo inverso, horario desde
  2020). Última tasa, percentil en ventana (default 30d), mediana, % horas
  positivas. **Todo en fracción**; el % sólo para mostrar, en campos aparte.
- **`btc_opciones`** — lee `opcion_diaria`. Dos planos: **agregado** (put/call por
  OI, OI total) como contexto; **max-pain de corto/medio plazo** (el imán del
  precio, como en Deribit) sobre los vencimientos hasta el trimestral cercano
  inclusive.

**La cadena de correcciones (la lección, no el resultado):** el primer diseño
reportaba "el strike de mayor OI" sobre todos los vencimientos → 70k a −11% del
spot, ambiguo. Medir el top-8 mostró que era **sedimento de calendario** (OI
sumado sobre 12 vencimientos). Corrección 1: cortar por vencimiento. Corrección 2:
detectar el trimestral **por su OI** (no por "mes trimestral" —matcheaba el
diario del 1-sep— ni por "último viernes" —hay 4 viernes—; lo define su tamaño).
Corrección 3, a partir de la pregunta de Migue "¿por qué no hacemos lo que hace
Deribit?": se verificó que **Deribit no sirve max-pain por API** —sólo da datos
crudos por instrumento—, así que "hacer lo que hace Deribit" es **calcular
max-pain**, su métrica, no inventar un "strike de mayor OI" que no correspondía a
nada. Resultado final: max-pain 72k a −9,38% del spot.

**Sub-lecciones de infraestructura:**
- **El caché vive en la tabla `valores`, no sólo en memoria.** Un `restart` carga
  el código nuevo pero NO fuerza recálculo (las capacidades cuelgan de
  `cierre_vela_diaria`). Tras deployar un cambio de cálculo:
  `DELETE FROM valores WHERE capacidad = '<nombre>';` y volver a pedirla. Señal de
  caché viejo: `desde_cache: true` + campos que ya no existen en el código.
- **La clave de caché es `capacidad` + `objeto_id` + `args`** — NO incluye el
  nombre en `objeto_id`. Todas las de mercado comparten `objeto='mercado'`,
  `objeto_id='mercado'`, `args={}`; las distingue la columna `capacidad`. Un
  DELETE debe filtrar por `capacidad`.

### 6.5 El planificador — 5 jobs, disciplina de eventos ✅

`backend/nucleo/planificador.py`. El diseño (arquitectura §7) pedía "eventos, no relojes"; el
código **ya lo implementa**, con los comentarios declarando el porqué de cada
horario.

| Job | Trigger | Rol |
|---|---|---|
| `cierre_del_dia` | 00:05 UTC | cierra la vela diaria (00:05, no 00:00: las fuentes aún cierran las suyas) |
| `reintentar_cierre` | cada hora en ventana | red de seguridad de lo irrecuperable (si la foto de ayer no se guardó) |
| `refrescar_coins` | cada 6 h | traer precios y ranking — "esto SÍ es temporal" |
| `catalogar_pares` | 01:30 UTC | catálogo de pares (después del inventario de coins) |
| `inventariar_coins` | 01:00 UTC | inventario completo de la fuente — detecta altas/bajas |

`cierre_del_dia` tiene `misfire_grace_time=7200`: si el proceso estuvo caído, se
dispara al levantarse dentro de 2 h; más tarde lo resuelve
`recuperar_dias_faltantes`. **Monitoreo:** `scripts/monitor.py` reporta qué pasó,
qué está en curso y huecos de historia. Verificado 2026-09-01: cadena
`cierre_del_dia → velas → capacidades` intacta, sin huecos.

### 6.6 Coin — capa INFORMACIÓN sobre una coin (construido esta sesión)

`backend/dominio/coin.py`, enganchado en `backend/app.py`. Tres capacidades
INDIVIDUAL sobre objeto `coin`, consulta **al pedido** (no masivas: el estado de
una coin puntual no se usa para comparar 3.000 entre sí). Primeras capacidades
sobre un objeto con id distinto de BTC.

- **`resolver_coin`** — la pieza base y **fuente de verdad** de "qué coin es
  'btc'": resuelve por id / symbol / nombre, priorizando el match más fuerte y,
  ante symbols repetidos, la de mejor puesto, informando las otras (`ambiguo`).
  Cuando el copiloto de skills se porte a v3, reusa esto.
- **`coin_estado`** — foto actual desde `coins`: precio, cap, volumen, puesto,
  variaciones 24h/7d. Verificado: `btc` → bitcoin, puesto 1. ✅
- **`coin_historia`** — evolución desde `coin_diaria`: cambio de precio y de
  puesto sobre la ventana. Declara los días realmente disponibles (la serie
  arrancó ~13/08: pedir 30 devuelve ~12 hoy). ✅
- **`coin_mercados`** — dónde se opera, desde `pares` por `coin_id`: exchanges,
  pares y mínimo de orden. Verificado: `eth` → 11 pares en MEXC/CoinEx. ✅

**Lo que queda ❌ declarado (falta de captura, no se inventó capacidad):** "qué
hace / sector / categorías" (`sector` y `categorias` vacíos en las 3.289 coins,
medido) y "supply" (no está en el esquema). Ambas requieren mapear campos de
CoinGecko que el sync no trae.

**Pulido pendiente (menor, no bloqueante):** `coin_mercados` no declara
`_fuente_hasta` (queda `null`); agregar el `capturado_at` de `pares` cuando se
retoque.

### 6.7 Contexto macro y estado de BTC — dominancia + compuesta (construido esta sesión)

Cierra la sección **Contexto macro** de la capa INFORMACIÓN y da la lectura de
estado de BTC sin recurrir a un régimen.

**Captura de `/global`** — el endpoint y su mapeo ya estaban declarados en
`fuentes.yaml` (dominancia btc/eth, cap total, volumen, coins activas). Se agregó
`capturar_global()` en `backend/captura/universo.py`, enganchada en
`_refrescar_coins` (misma fuente, misma cadencia; si `/global` falla no tumba el
refresco de coins). Tabla `mercado_global` (migración 010), una fila por día.

**`mercado_dominancia`** — la brújula: dominancia BTC/ETH, cap y volumen totales,
y el cambio en puntos porcentuales sobre la ventana. Vigencia `refresco_de_coins`
(el segundo evento de invalidación vivo). Declara que la dominancia es un cociente
derivado y reporta `coins_activas_fuente` (el denominador que puede moverse solo).
Verificado: BTC 59,23 %, ETH 11,08 %.

**`btc_estado`** — compuesta que **reúne** perfil + funding + opciones +
dominancia: las cuatro caras del estado de BTC en una lectura, sin etiqueta. Es la
respuesta de v3 a "¿cómo está BTC?" en vez de un régimen. Composición **anidada**
(perfil trae adentro sus 5 dimensiones) — la primera del sistema. Verificado: 4 de
4 componentes, epistémica compuesta hacia arriba (hereda los límites de las 9
mediciones subyacentes).

**Dos hallazgos de diseño que expuso la primera composición heterogénea:**

1. **Parámetros heterogéneos.** El motor propaga los `parametros` de la compuesta
   a todos sus componentes y valida estricto; `btc_estado` declaraba `ventana`
   pero `btc_funding` sólo admite `dias` → rechazo. **Regla:** una compuesta no
   declara parámetros que sus componentes nombran distinto — el estado es una
   reunión de fotos, cada una con su propia noción de ventana. Si en el futuro se
   repite mucho, evaluar que el motor propague selectivamente (mejora aparte).
2. **Fuentes de granularidad mixta.** El motor calcula `fuente_hasta` de una
   compuesta como el `min()` de las de sus componentes; `btc_estado` mezcló una
   fuente horaria (funding: `datetime`) con diarias (opciones, dominancia:
   `date`) y `min()` lanzaba "can't compare datetime to date". **Arreglo de núcleo
   (motor.py):** normalizar `date`→`datetime(UTC)` sólo para comparar, devolviendo
   el valor original. Ahora cualquier compuesta puede mezclar fuentes de cualquier
   granularidad — mejora permanente, no un parche.

---

## 7. Datos, eventos y vigencia

### 7.1 Qué se guarda y qué no

> **Se guarda lo que no se puede volver a pedir. Lo que la fuente devuelve
> on-demand se calcula al vuelo.** Segundo eje: lo que se necesita a escala y con
> frecuencia se guarda por latencia aunque sea recuperable.

Se guarda: foto diaria del universo de coins (irrecuperable — la fuente no da el
ranking de hace un mes), velas diarias de todos los pares (recuperables pero se
usan en cada consulta sobre miles de pares), señales de estrategias y desenlaces,
lecturas de las señales del régimen. **No** se guarda: velas horarias de todo el
universo (on-demand, de a un par), libro de órdenes en régimen permanente (el
error de v2 que generó 3,9 GB para 2 pares).

**Tres modos de cálculo**, y el criterio que decide entre los dos últimos es *¿la
métrica se usa para comparar objetos entre sí?*:

| Modo | Cuándo | Ejemplos |
|---|---|---|
| **Al vuelo** | barato o cambia constantemente | precio, spread, agregados del universo |
| **Por evento, para todo el universo** | se usa para **comparar** objetos entre sí | rango, oscilación, repetibilidad |
| **Al pedido, con caché** | caro y se consulta **de a uno** | estadísticas horarias, curva de profundidad |

> Nadie va a rankear 3.000 pares por en qué franja hacen su máximo (al pedido); sí
> por rango (por evento, para todos).

### 7.2 Los cinco eventos

Casi todo lo que en v2 corría por reloj cuelga de un evento. Cuatro son "llegaron
datos nuevos"; el quinto es "pasó algo".

| Evento | Qué dispara |
|---|---|
| cerró la vela diaria | rango, oscilación, repetibilidad, y las capacidades `*` |
| cerró la vela horaria | *(sin consumidores por ahora)* |
| llegó un refresco de coins | snapshot diario, agregados del universo |
| cambió el universo | alta, baja o cambio de estado *(el que v2 no tenía)* |
| se disparó una señal | notificación y registro |

### 7.3 Vigencia y caché

Toda respuesta viaja con su vigencia — no es opcional cuando el consumidor razona.
Cada resultado declara `calculado_at` (cuándo se calculó), `fuente_hasta` (hasta
qué dato llegan los insumos — **distinto** de lo anterior: si se calcula a las
15:00 con velas hasta ayer, la métrica cubre hasta ayer) y `vigente_hasta` /
`vigente_evento`.

**La vigencia se declara por evento antes que por tiempo** ("vale hasta que cierre
la vela diaria", no "vale 6 horas", que es arbitrario). El caché es transparente
—quien llama no sabe si se calculó o se sirvió— pero la vigencia siempre viene en
la respuesta. Ante un vencido: se devuelve el anterior **marcado** y se recalcula
en segundo plano; una misma capacidad+args ya en curso no se dispara dos veces.

> Mostrar el dato anterior sólo es honesto si viene declarado desde cuándo es.
> Sin eso sería el problema de v2: datos viejos presentados como actuales.

---

## 8. Inventario y deuda — re-medido (2026-09-02)

El fundacional del 16/08 puso "levantar el inventario de v2" como lo primero, con
hallazgos preocupantes. **La medición de hoy muestra que v3 arrancó de una base
limpia: el inventario está saldado por construcción, no como deuda pendiente.**

### 8.1 La base de datos hoy

Total ~230 MB, y **no hay una sola tabla-basura en el top**:

| Tabla | Tamaño | Filas |
|---|---|---|
| `vela_diaria` | 172 MB | 1.010.502 |
| `btc_vela_horaria` | 20 MB | 79.140 |
| `coin_diaria` | 8,8 MB | 37.861 |
| `funding_btc` | 5,7 MB | 58.463 |
| `inventario` | 5,6 MB | 19.480 |
| `valores` | 5,6 MB | 8.960 |
| `universo_eventos` | 5,0 MB | 22.648 |
| `opcion_diaria` | 1,7 MB | 5.034 |
| `pares` | 1,7 MB | 3.017 |
| `coins` | 1,5 MB | 3.289 |
| *(resto: btc_vela_diaria, ejecuciones, eventos, halvings, métricas…)* | <1 MB c/u | — |

### 8.2 Los hallazgos del 16/08, actualizados

| Hallazgo del fundacional (16/08) | Estado hoy (02/09) |
|---|---|
| `ob_snapshots` = 98% de la base (3,9 GB para 2 pares) | ✅ **no existe en v3** |
| 4 tablas del bot v1 sin lectores | ✅ **no existen** (`bot_%` → 0 filas) |
| `strat_signals` con 36k filas, 1 estrategia | ✅ **no existe** (`%strat%` → 0) |
| Endpoints y tablas heredados de v1 | ✅ esquema nuevo: migraciones 001→009, todas de v3 |
| 18 capacidades declaradas, 8 usadas | recontado: **12 declaradas** (runtime, = 12 en archivos vivos; un grep previo contó 15 por incluir `.bak`) |
| `alerts_job` cada minuto para 2 alertas | n/a — no portado a v3 |

**v3 no arrastró la deuda de v2: se construyó de cero en una base nueva.** Las
migraciones (`001_universo_coins` … `009_funding`, fechadas 24-29/08) definen todo
el esquema. El inventario que el fundacional pedía "hacer" ya está hecho — por no
haber traído nada que inventariar.

### 8.3 Deuda real que sí queda (honesto)

- **Brecha diseño/implementación en operaciones:** 1 de 8 (`reunir`). Clasificar,
  agregar, filtrar/ordenar, detectar discrepancia, proyectar, simular — ninguna
  existe aún. Todo lo de investigación y desarrollo depende de ellas.
- **`regimen_btc` no existe en v3.** El diseño lo usa como ejemplo central
  (clasificar 12 señales) y sigue mencionado en docstrings de `capacidades.py` y
  `motor.py`, pero **no está implementado** (verificado 02/09: sin declaración,
  sin módulo, ausente de `/api/capacidades`). Es el consumidor natural de la
  operación `clasificar` cuando exista.
- **Módulos conversacionales viejos** (`chat.py`, orquestador, `chat_groq`): ✅
  no existen en v3 (verificado 02/09). Ya no es deuda.
- **Widgets, vistas invocables, estado de trabajo persistido:** diseñados, no
  construidos en v3.

---

## 9. Método y principios

Valen tanto como el código. Migue los impuso al ritmo de trabajo.

**Epistémica y disciplina de hipótesis:**
- **La pregunta primero, el dato después.** Hipótesis con regla de rechazo escrita
  *antes* de mirar los datos. No inventar qué medir porque hay datos disponibles.
- Medir contra **tasas base**; verificar robustez **across ventanas**; comparar
  toda estrategia contra "comprar y no hacer nada" neto de costos.
- Cada crypto tiene un rango diario explotable, pero el rango es **simétrico**:
  entrar sin criterio equivale a cara o cruz. El edge viene de saber algo del día
  *antes* de entrar, y ese criterio se descubre por par.

**Arquitectura:**
- "Lo que hay que recordar se olvida; lo declarado, no."
- Estado del dato (activa/inactiva — lo declara la fuente) separado de si lo
  seguimos (decisión nuestra).
- Las capacidades declaran MIDE / INFIERE / NO SABE explícitamente.
- Skills orquestadas por código, no por autonomía del LLM.
- Data-para-razonar y data-para-mostrar en rieles separados.

**Proceso:**
- **Una hipótesis, una medición, un cambio, un commit.** No apilar parches.
- **Medir antes de decidir.** Diagnosticar por medición, no por conjetura. (Se
  perdieron horas por diagnosticar con exceso de confianza; el problema real
  —89k tokens— sólo apareció al instrumentar.)
- **No parchar el síntoma** — atacar la causa.
- **Commitear los puntos estables** — en cada hito.
- **Verificar el estado real del server, no suponerlo** — `grep`/`psql` sobre el
  código y la DB, no la memoria de qué se subió. *(Este mismo documento salió de
  eso.)*

**Modo de trabajo (fijo):** el asistente lee el repo directo (no pide pegar
código ni correr `psql`/`cat`/`grep` para contenido que ya está en el repo);
entrega archivos completos listos para descargar; da comandos scp
(PowerShell, origen `C:\Users\Migueh\Downloads`) y bash/ssh para migraciones y
systemd; usa parches (`parche_*.py`) para no pisar correcciones locales. Migue no
edita a mano.

**Lo que falló y por qué (para no repetirlo):**
- Multi-agente: el LLM consumía datasets crudos (89k tokens) → límite de TPM. La
  "secretaria consolidadora" y la poda de campos movían el problema, no lo
  resolvían.
- Una columna por capacidad en el esquema: falla cuando el copiloto puede crear
  capacidades nuevas (exige migración cada vez) → tabla `valores` genérica.
- "Régimen = asignar etiqueta" era el framing equivocado → "describir el estado en
  varias dimensiones sin etiqueta obligatoria" (`btc_perfil`).
- Promedio simple en el mapa de sectores daba lecturas invertidas → promedio
  ponderado por capitalización.

---

## 10. El copiloto

> **Estado (05/09):** el **escalón 1 está VIVO** (ver §10.7). Se conversa con
> AXIOM: `POST /api/copiloto` clasifica, ejecuta capacidades por el motor y
> redacta con datos medidos. Los escalones 2-5 (widgets declarados, frontend,
> operar vistas, crear) siguen siendo diseño. El resto de esta sección mezcla lo
> implementado (marcado ✅) con el diseño de lo que falta.

### 10.0 El cliente de LLM — multi-proveedor, multi-nivel (✅ 05/09)

`backend/llm/cliente.py`. **Un** cliente que habla formato **OpenAI-compatible**
—el estándar que hablan Gemini (endpoint `/openai`), Groq, OpenRouter—. Los
proveedores y los modelos son **configuración del `.env`**, no código.

> **La lección de v2, recuperada.** v2 ya había concluido que la robustez no
> viene de "elegir el modelo perfecto" sino de **desacoplarse del proveedor**:
> cualquier modelo se satura (429), se cae (503) o lo retiran (404). Lo vivimos
> en carne propia el 05/09 —`gemini-2.0-flash` retirado, `3.6-flash` con cuota
> agotada, `flash-latest` con 503, todos el mismo día—. La solución no fue un
> modelo, fue esta arquitectura.

Dos dimensiones, resueltas juntas:
- **Nivel de tarea.** El copiloto pide un **nivel**, no un modelo: `rapido`
  (clasificar, redactar) o `capaz` (crear estrategias, razonamiento
  estructurado). Cada nivel es una cadena de `proveedor:modelo`.
- **Disponibilidad.** La cadena de un nivel **cruza proveedores**: si `gemini:…`
  cae, salta a `groq:…` transparentemente. Nunca sin copiloto.

Config actual (en `.env`): proveedores `gemini,groq`;
`rapido = gemini:gemini-flash-lite-latest, groq:openai/gpt-oss-20b, …`;
`capaz = groq:openai/gpt-oss-120b, gemini:gemini-3.7-flash, …`. Agregar
OpenRouter (o cualquiera OpenAI-compat) es una línea más, sin tocar código.

Verificado: `rapido` clasifica con el lite de Gemini; `capaz` razona con
gpt-oss-120b de Groq; el fallback salta ante 404/429/503.

### 10.1 Por qué el copiloto es el centro, y qué significa

v3 existe para que se **converse** con el mercado (§1.3). El copiloto no es una
sección más: es la forma principal de preguntarle al sistema. Pero "centro" no
quiere decir "única puerta". El fundacional define tres modalidades que no
compiten:

- **Preguntar** — hay una pregunta formada → el copiloto responde.
- **Explorar** — no hay pregunta, se quiere mirar → las **secciones**.
- **Acompañar** — se está mirando algo y surge la pregunta → se pregunta *desde*
  la sección, con contexto.

La relación entre secciones y copiloto quedó decidida (04/09): **las vistas y
widgets existen declarados; navegarlos por menú y pedírselos al copiloto son dos
formas de operar lo mismo.** El copiloto es *otra forma* de operar las vistas, no
su dueño. Misma casa, dos puertas. Esto es lo que evita el error de v2 (pantallas
que consultan datos por su cuenta): en v3 la sección y el copiloto tocan el mismo
widget declarado, que consume la misma capacidad.

> **Consecuencia de diseño:** el contexto dice SOBRE QUÉ hablar, no CON QUÉ datos.
> Cuando el copiloto sabe que estás en Gráficos con ROSE/BTC, "¿cómo lo ves?" se
> resuelve trayendo las capacidades que haga falta — no queda limitado a lo que
> la pantalla ya cargó.

### 10.2 Las cuatro etapas (heredadas de v2, adaptadas a v3)

El copiloto de skills de v2 estableció el patrón, y se conserva porque resolvió
de raíz el problema que hundió al enfoque multi-agente (el LLM tragando datasets
crudos de ~89k tokens en loops). **El código orquesta; el LLM sólo entiende y
redacta.** Cuatro etapas:

1. **Clasificar intención** (LLM, decisión 04/09) — el mensaje + el objeto en
   foco (§10.4) → intención + target + parámetros, como JSON estructurado. En v2
   esto era regex; se pasó a LLM porque la regex tiene techo bajo: agarra
   "contame de ONT" pero no "¿cómo viene BTC contra el mercado?" ni "¿qué opciones
   tiene ethereum?" sin volverse un nido de patrones frágiles. **Contrapartida
   asumida:** ahora hay DOS llamadas al LLM por turno (clasificar + redactar), no
   una — v2 tenía una sola. Se acepta porque la clasificación es la puerta a todo
   lo demás. La llamada de clasificación debe ser **barata y acotada**: prompt
   corto, salida JSON (`intencion`, `target`, `parametros`), `max_tokens` bajo. No
   redacta; decide.
2. **Resolver target** (código) — "ONT" → coin_id "ontology" (en v3, la función
   `resolver_coin` de §6.6, que es la fuente de verdad).
3. **Ejecutar + destilar capacidades** (código, en paralelo) — la intención mapea
   a un set de capacidades. El código las resuelve por el motor y **destila**:
   toma sólo el carril `destila`, nunca la `presentacion`.
4. **Redactar** (1 llamada LLM) — recibe el material destilado + la disciplina
   epistémica, y redacta. Sin loop, sin tool-calling.

> **Optimización futura, a medir (no implementar de entrada):** un **atajo de
> reglas** antes del LLM para los casos triviales e inequívocos (un símbolo
> conocido suelto, un comando directo) los resolvería sin la primera llamada,
> devolviendo a esos casos el costo de una sola llamada. Pero es optimización:
> se arranca con "siempre clasifica el LLM" y se agrega el atajo sólo si la
> latencia de la doble llamada molesta —medir antes de optimizar—.

Resultado en v2 (con clasificación por regex, una sola llamada): ~5 s, cero
errores de contexto (contra ~10 de 11 fallos y 45-94 s del multi-agente). En v3,
con clasificación por LLM, son dos llamadas por turno; sigue lejos del
multi-agente en costo y fiabilidad porque ninguna de las dos traga datasets
crudos. El LLM de producción es **Gemini Flash** (rápido y barato, lo que ayuda a
absorber la segunda llamada).

**Lo que cambia en v3** respecto del experimento de v2: la etapa 3 resuelve
capacidades por el **motor** (`Motor.resolver`), que ya compone lo epistémico y
respeta vigencia/caché — no llama funciones sueltas. Y la clasificación es por LLM
con el foco como contexto (arriba).

### 10.3 El copiloto no sólo responde: OPERA

Esto es lo nuevo de v3, lo que el experimento de v2 no tenía (era texto→texto sin
UI). El copiloto **actúa sobre la aplicación**. Tres tipos de acción, de menor a
mayor complejidad:

- **Montar** — traer un widget a la conversación: "¿cómo está BTC?" → monta el
  widget de `btc_estado`.
- **Navegar / operar una vista** — "mostrame el gráfico de ROSE" (navega),
  "agregá una EMA de 21" (opera la vista donde estás, sin tocar su JS: opera
  sobre lo que la vista **declaró** que acepta).
- **Crear** — "creá una estrategia que…" → el copiloto **escribe una
  declaración** (un dato: condiciones, stop, target), no código. Igual con
  indicadores y colecciones.

Que crear sea escribir una declaración es lo que hace posible que el copiloto
cree cosas sin escribir Python — y es coherente con "estrategias como datos"
(§1) y con la tabla `valores` genérica (el copiloto crea capacidades dinámicas).

### 10.4 El contrato copiloto ↔ frontend

Cómo el copiloto le dice al frontend qué hacer. Dos modelos, y v3 usa **los dos
según el caso**, sobre el mismo catálogo declarado:

- **Modelo respuesta (montar).** El copiloto devuelve texto + una lista de
  widgets a renderizar: `{ texto, widgets: [{ widget, args }] }`. El frontend los
  monta en el hilo. Es el subconjunto con el que se empieza, y cubre "Preguntar".
- **Modelo acción (operar).** El copiloto devuelve **acciones** sobre el estado de
  UI: `{ accion: "navegar", vista, args }`, `{ accion: "operar", vista, cambio }`,
  `{ accion: "crear", tipo, declaracion }`. El frontend las aplica sobre su
  estado. Es lo que permite "agregá una EMA" y "activá esta estrategia".

Ambos modelos referencian **widgets y vistas por su nombre declarado** — el
copiloto nunca manda HTML ni JS, manda referencias a cosas que el catálogo
conoce. Eso es lo que hace que el mismo widget lo monte una sección o el copiloto,
indistintamente.

**El objeto en foco** (decisión 04/09, "lo más eficiente"). Para que el copiloto
opere la vista donde estás y resuelva referencias ("¿cómo lo ves?"), el frontend
manda con cada mensaje un **foco mínimo**, no su estado completo:
`foco: { vista, objeto, parametros_clave }` — p. ej. `{ vista: "grafico", par:
"ROSE/BTC", temporalidad: "1d" }`. Se eligió esto sobre las alternativas por
eficiencia y por fidelidad al fundacional (*"el contexto dice SOBRE QUÉ hablar, no
CON QUÉ datos"*):
- **no** el estado completo de la UI en cada turno (payload inflado, el error del
  multi-agente);
- **no** estado de sesión en el backend (sincronización y complejidad que no
  rinde con un usuario).

El foco es barato de mandar, suficiente para operar, y **entra como contexto de la
clasificación** (§10.2): el LLM recibe mensaje + foco y resuelve intención y
referencia en una pasada. "¿cómo lo ves?" sin foco es inclasificable; con
`foco: {par: ROSE/BTC}` la intención es "análisis del par en foco". El foco no es
un extra: es lo que hace clasificable la conversación con contexto.

> **Regla de confirmación** (del fundacional): la línea no está en si el copiloto
> escribe, sino en si queda algo funcionando por su cuenta. *Directo* (se deshace
> fácil: watchlist, mostrar gráfico, poner indicador) → sin confirmación. *Con
> confirmación* (activar una estrategia que empezará a notificar, borrar cosas con
> historia) → el copiloto propone y espera el sí.

### 10.5 Qué declara un widget

El widget es el puente entre una capacidad y su representación. **Declaración en
backend, render en frontend** (de lo mejor de v2, se conserva). Un widget declara:

- **`consume`** — qué capacidad alimenta el widget (`btc_estado`,
  `mercado_dominancia`…).
- **`contextos`** — dónde puede aparecer: `pantalla`, `panel`, `chat`,
  `dashboard`. El mismo widget sirve al copiloto (en `chat`) y a una sección (en
  `pantalla`).
- **`densidades`** — qué campos se muestran según el ancho disponible (compacto /
  normal / amplio).
- **`acepta`** — lo que se le puede pedir a la vista. Es lo que v2 no tenía y v3
  necesita: hace posible que el copiloto opere la vista sin conocer su JS. Un
  gráfico declara `acepta: { par, temporalidad: [1m…1d], indicadores: [{tipo,
  periodo}], rango }`.

El widget consume el carril `presentacion` de la capacidad (nunca `destila`, que
es para el LLM). Los dos carriles viajan separados desde la capacidad (§5.4): lo
que ve el modelo y lo que ve la pantalla no se mezclan.

### 10.6 Qué declara una vista invocable

Una vista es un widget con estado propio del usuario (`es_espacio_de_trabajo:
true`): un gráfico con sus indicadores, un screener con sus filtros. Lo que la
distingue es que el copiloto puede **operarla en curso** — cambiar su estado sin
recrearla. Su `acepta` es el vocabulario de esa operación: el copiloto traduce
"agregá una EMA de 21" a un cambio sobre `indicadores`, y el frontend lo aplica.

### 10.7 Orden de construcción

En orden de dependencia. El escalón 1 está hecho (05/09):

1. ✅ **Copiloto de skills en v3** — las cuatro etapas contra el motor
   (`backend/copiloto/`). Clasificar (LLM, nivel rápido) → resolver (`resolver_coin`)
   → ejecutar capacidades en paralelo por el motor → redactar (LLM, nivel rápido).
   Router `POST /api/copiloto`. Texto→texto (Modelo respuesta). **Verificado:**
   estado de BTC, info de coin y dominancia redactan con datos reales, percentiles
   traducidos a lectura, sin predecir. Intenciones mapeadas hoy: `estado_btc`,
   `posicionamiento_btc`, `dominancia`, `info_coin`, `historia_coin`.
2. **Catálogo de widgets declarados** — declarar `consume`/`contextos`/
   `densidades`/`acepta` para las capacidades que ya existen (`btc_estado`,
   `coin_*`, `mercado_dominancia`).
3. **Frontend mínimo centrado en conversación** — el copiloto al centro, montando
   widgets del catálogo (Modelo respuesta). Las secciones navegables comparten
   esos widgets.
4. **Modelo acción** — navegar y operar vistas. Acá entran los espacios de
   trabajo (el gráfico) y el `acepta`.
5. **Crear** — el copiloto escribe declaraciones (indicadores, luego estrategias).
   Lo último, porque "crear" que persiste y opera es lo de mayor riesgo.

Cada escalón es usable solo: con (1)+(2)+(3) ya se conversa con el mercado y se
ven las respuestas. (4) y (5) son lo que ninguna otra plataforma tiene, y por eso
van al final —con más base debajo—.

---

## 11. Qué sigue

**El copiloto y el frontend (el centro de v3 — §10; escalón 1 ✅, faltan 2-5):**
- ✅ **Copiloto de skills** (05/09) — se conversa con AXIOM por `POST /api/copiloto`.
  Cliente LLM multi-proveedor/multi-nivel (Gemini + Groq). Falta lo demás.
- **Catálogo de widgets declarados + frontend mínimo** — declarar
  `consume`/`contextos`/`densidades`/`acepta` para las capacidades que ya existen,
  y una UI centrada en la conversación que los monte. Página en blanco hoy; el
  server ya sirve `frontend/` por StaticFiles. Es el escalón 2-3.
- **Operar vistas y crear** (escalones 4-5) — el Modelo acción y que el copiloto
  escriba declaraciones (indicadores, estrategias). "Crear" usa el nivel `capaz`
  del LLM (Groq gpt-oss-120b), ya disponible y esperando.

**Investigación (la tesis de v3):**
- **Rango diario explotable por par** — descubrir la regla de rango inherente a
  cada crypto (hipótesis central). Metodología: hipótesis con regla de rechazo
  antes de mirar, tasa base, robustez por ventana, comparación contra
  buy-and-hold neto de costos. Analizar pares por tramo de capitalización.
- Necesita **velas horarias por par** (hoy sólo hay de BTC), y el otro lado de la
  ecuación: las estrategias como datos.

**Arquitectura (desbloquea capas enteras):**
- **Implementar más operaciones** — la más urgente es *comparar contra su
  historia* como operación genérica (hoy cada capacidad la reimplementa), luego
  *filtrar y ordenar* (habilita el screener y "pares para operar rangos") y
  *agregar* (habilita sectores). *Clasificar* quedó sin consumidor urgente al
  descartarse el régimen (§2.1).
- **Estrategias como datos** — el catálogo declarativo que responde la pregunta 7
  y cierra la capa de desarrollo. Es también el último escalón del copiloto (§10.7).

**Completar INFORMACIÓN (lo que queda de la capa base):**
- **Capturar sector/categorías/supply** — CoinGecko los da (mapeados en
  `fuentes.yaml`), pero el sync no los lleva a tabla. Cierra "qué hace / supply"
  de Coins y desbloquea sectores. Es lo más barato que queda.
- **Pares — consulta de par individual** — calcado a `coin.py`; el dato y las
  capacidades masivas ya existen.
- **Fuentes nuevas:** noticias, desbloqueos (eventos con fecha conocida de
  antemano — especialmente valiosos), sentimiento, on-chain (con fuente confiable,
  no el scraping frágil de v2).

**Pulido pendiente:**
- Migrar las capacidades de coin a la vigencia `refresco_de_coins` (hoy usan
  `cierre_vela_diaria` provisorio).
- `coin_mercados` sin `_fuente_hasta`.

---

## Cómo retomar

1. Leé este documento.
2. Verificá salud: `venv/bin/python scripts/monitor.py --horas 30` y
   `curl -s http://localhost:8003/api/capacidades`.
3. Elegí frente (§11). El cierre natural de la última sesión es **exponer el
   posicionamiento al copiloto**; la tesis de fondo es el **rango diario por par**;
   lo que desbloquea más es **implementar operaciones** más allá de `reunir`.

> **Nota de método final.** Este documento reemplaza cinco archivos que mezclaban
> diseño (condicional, 16-18/08) con implementación real y ya se contradecían
> entre sí. Cada número de la §6 y la §8 está medido contra el server el
> 2026-09-02. Donde hay diseño no implementado, se marca ❌. La disciplina que v3
> hereda de v2 no es qué código conservar, sino qué preguntas hacerle a un dato
> antes de confiar en él — y eso incluye a este documento.
