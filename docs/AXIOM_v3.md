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
2. Qué tiene que poder responder
3. La arquitectura — capacidades y operaciones
4. Cómo se declara cada pieza
5. Estado real de implementación (verificado 2026-09-02)
6. Datos, eventos y vigencia
7. Inventario y deuda — re-medido
8. Método y principios
9. Qué sigue

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

### 3.5 Los objetos

- **Coin** — un activo del ecosistema (universo CoinGecko).
- **Par** — un mercado concreto: activo + quote + exchange (operable en MEXC /
  CoinEx).
- **Mercado** — el agregado / BTC como referencia.

El vocabulario cumple una segunda función: además de nombrar propiedades, dice
**sobre qué objeto valen**. Eso restringe las composiciones válidas —nada de
"agregar el spread de un sector de coins"— y es lo que un motor de validación
usa para rechazar composiciones sin sentido.

---

## 4. Cómo se declara cada pieza

> El diseño original (`declaraciones.md`) mostraba formato YAML, marcándolo como
> ilustrativo. **La implementación real declara en Python** vía
> `registro.registrar(Simple(...))` / `registro.registrar(Compuesta(...))` en los
> módulos de `backend/dominio/`, llamados desde `declarar()` de cada módulo. Lo
> que sigue describe QUÉ se declara; la forma es el objeto Python.

### 4.1 Qué es código y qué es dato

| Pieza | Forma | Por qué |
|---|---|---|
| Motor y operaciones | código | pocos y estables |
| Fuentes | dato | cambian cuando cambia una API |
| Capacidades simples | dato/decl. | son muchas y se agregan seguido |
| Capacidades compuestas | dato/decl. | cambiar qué señales usa un régimen no debe requerir código |
| Widgets | dato (decl.) + código (render) | ya funcionaba así en v2 |
| Estrategias | dato | **el copiloto las crea**: no puede escribir código |

El criterio: **si lo vas a cambiar seguido, es dato.**

### 4.2 Una capacidad simple declara

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

### 4.3 Una capacidad compuesta declara además

- **de qué se compone** (nombres de capacidades), **con qué operación**, **con
  qué parámetros** (defaults que el pedido puede sobrescribir, quedando
  registrados)
- **el resultado incluye el estado de sus componentes**: si se calculó con 10 de
  12 señales, eso cambia la lectura y no puede quedar oculto — sale de la
  estructura.

### 4.4 Data-para-razonar y data-para-mostrar viajan separadas

Cada capacidad declara su `destila` (campos destinados al razonamiento, que ve el
LLM) y su `presentacion` (campos para el widget del frontend, que **nunca** se
mandan al LLM). Es lo que evita que el modelo consuma datasets crudos que no debe
procesar (ver §5.2).

---

## 5. Estado real de implementación (verificado 2026-09-02)

Esta es la sección que a los cuatro documentos de diseño les faltaba: **qué está
construido y corriendo, medido contra el server.**

### 5.1 Infraestructura

- Servidor personal **`decentralia`** (192.168.0.88), Debian. Python por pyenv,
  venv en `/home/migue/apps/axiom-v3/`. PostgreSQL 17.
- **v3 corre en el puerto 8003**, servicio systemd **`axiom-v3.service`**.
- **v2 quedó congelada en 8002** (`axiom-v2.service`), corriendo sólo para
  preservar su historia. No se toca.
- Repo: `github.com/emeache25-axiom/axiom-v3`. Deploy por **parches y archivos
  que cambian** (no paquetes completos, para no pisar correcciones locales); scp
  desde `C:\Users\Migueh\Downloads`.

### 5.2 El giro de AGENTES a SKILLS

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

### 5.3 Las 12 capacidades declaradas

Fuente autoritativa: `GET /api/capacidades` → **total: 12**. Una sola operación
implementada: **`reunir`**.

**Mercado / BTC-referencia (9):**

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

**Par (3):** `oscilacion`, `rango_tipico`, `repetibilidad` — las tres **masivas**
(todo el universo de pares por evento). Son "la mitad medida" de la ecuación de
estrategias (§9): describen el comportamiento del par que un catálogo de
estrategias cruzaría con sus requisitos.

Las cinco dimensiones de BTC son **independientes por diseño** (correlaciones
bajas a 30 días); `btc_perfil` deliberadamente **no colapsa en una etiqueta**
—"alcista"/"bajista" destruiría lo que distingue un mercado que sube tranquilo de
uno que sube violento—.

### 5.4 Posicionamiento (Deribit) — construido esta sesión

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

### 5.5 El planificador — 5 jobs, disciplina de eventos ✅

`backend/nucleo/planificador.py`. El diseño (§6) pedía "eventos, no relojes"; el
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

---

## 6. Datos, eventos y vigencia

### 6.1 Qué se guarda y qué no

> **Se guarda lo que no se puede volver a pedir. Lo que la fuente devuelve
> on-demand se calcula al vuelo.** Segundo eje: lo que se necesita a escala y con
> frecuencia se guarda por latencia aunque sea recuperable.

Se guarda: foto diaria del universo de coins (irrecuperable — la fuente no da el
ranking de hace un mes), velas diarias de todos los pares (recuperables pero se
usan en cada consulta sobre miles de pares), señales de estrategias y desenlaces,
lecturas de las señales del régimen. **No** se guarda: velas horarias de todo el
universo (on-demand, de a un par), libro de órdenes en régimen permanente (el
error de v2 que generó 3,9 GB para 2 pares).

### 6.2 Los cinco eventos

Casi todo lo que en v2 corría por reloj cuelga de un evento. Cuatro son "llegaron
datos nuevos"; el quinto es "pasó algo".

| Evento | Qué dispara |
|---|---|
| cerró la vela diaria | rango, oscilación, repetibilidad, y las capacidades `*` |
| cerró la vela horaria | *(sin consumidores por ahora)* |
| llegó un refresco de coins | snapshot diario, agregados del universo |
| cambió el universo | alta, baja o cambio de estado *(el que v2 no tenía)* |
| se disparó una señal | notificación y registro |

### 6.3 Vigencia y caché

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

## 7. Inventario y deuda — re-medido (2026-09-02)

El fundacional del 16/08 puso "levantar el inventario de v2" como lo primero, con
hallazgos preocupantes. **La medición de hoy muestra que v3 arrancó de una base
limpia: el inventario está saldado por construcción, no como deuda pendiente.**

### 7.1 La base de datos hoy

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

### 7.2 Los hallazgos del 16/08, actualizados

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

### 7.3 Deuda real que sí queda (honesto)

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

## 8. Método y principios

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

## 9. Qué sigue

Con el inventario saldado (§7) y las dos capacidades de posicionamiento cerradas,
los frentes abiertos, con su estado:

**Integración (cierra lo construido):**
- **Exponer funding + opciones al copiloto** — que el copiloto responda "¿cómo
  está el posicionamiento de BTC?" destilando funding + max-pain. Requiere definir
  `destila`/`presentacion` de ambas y engancharlas al flujo de skills. Es el paso
  natural para que las capacidades de esta sesión le sirvan a alguien.
- **`btc_perfil` en el copiloto** — ya existe como compuesta; falta que el
  copiloto la sepa invocar y redactar.

**Investigación (la tesis de v3):**
- **Rango diario explotable por par** — descubrir la regla de rango inherente a
  cada crypto (hipótesis central). Metodología: hipótesis con regla de rechazo
  antes de mirar, tasa base, robustez por ventana, comparación contra
  buy-and-hold neto de costos. Analizar pares por tramo de capitalización.
- Ya medido de este lado: `rango_tipico`, `oscilacion`, `repetibilidad`. Falta el
  otro lado de la ecuación (§4.3 del diseño): las estrategias como datos.

**Arquitectura (desbloquea capas enteras):**
- **Implementar más operaciones** — la más urgente es *comparar contra su
  historia* como operación genérica (hoy cada capacidad la reimplementa), luego
  *clasificar* (habilita `regimen_btc`) y *filtrar y ordenar* (habilita el
  screener y la pregunta 2 sobre coins).
- **Estrategias como datos** — el catálogo declarativo que responde la pregunta 7
  y cierra la capa de desarrollo.

**Fuentes nuevas (preguntas hoy imposibles):**
- **Desbloqueos / eventos temporales** (pregunta 6) — datos con eje temporal, no
  propiedades de un objeto; no entran en las ocho operaciones, necesitan su propia
  vía de acceso. Los desbloqueos son especialmente valiosos: eventos con fecha
  conocida de antemano.

---

## Cómo retomar

1. Leé este documento.
2. Verificá salud: `venv/bin/python scripts/monitor.py --horas 30` y
   `curl -s http://localhost:8003/api/capacidades`.
3. Elegí frente (§9). El cierre natural de la última sesión es **exponer el
   posicionamiento al copiloto**; la tesis de fondo es el **rango diario por par**;
   lo que desbloquea más es **implementar operaciones** más allá de `reunir`.

> **Nota de método final.** Este documento reemplaza cinco archivos que mezclaban
> diseño (condicional, 16-18/08) con implementación real y ya se contradecían
> entre sí. Cada número de la §5 y la §7 está medido contra el server el
> 2026-09-02. Donde hay diseño no implementado, se marca ❌. La disciplina que v3
> hereda de v2 no es qué código conservar, sino qué preguntas hacerle a un dato
> antes de confiar en él — y eso incluye a este documento.
