# AXIOM v3 — Documento fundacional

> Escrito el 16/08/2026. Reemplaza a la premisa parcial de v2 y a los supuestos
> con los que se venía construyendo.
>
> **Este documento no decide la arquitectura.** Define qué es AXIOM, qué tiene
> que poder responder y con qué garantías. La arquitectura se diseña después,
> desde acá.

---

## 1. Por qué v3 no es v2 mejorada

La v2 se pensó como **un cockpit que muestra datos de mercado**. Después
aparecieron Kepler y el copiloto, y el requisito de fondo cambió sin que nadie
reescribiera la premisa. Se siguió construyendo sobre una visión que ya no
alcanzaba.

Un sistema que **muestra** datos y uno que **razona sobre** datos necesitan cosas
distintas. El primero tolera un dato viejo o ambiguo: el trader lo mira, lo
interpreta, lo descarta. El segundo lo toma como verdad y construye encima.

Eso explica por qué todos los problemas encontrados en la última semana son del
mismo tipo. No fueron errores de cálculo — fueron **datos que mentían en
silencio**:

| Encontrado | Cuánto llevaba |
|---|---|
| Bot v1 ejecutándose tras ser reemplazado, fallando cada 5 min | 2 meses |
| Sync perdiendo 250 coins por corrida (un `continue` mal puesto) | semanas |
| Precios redondeados a cero por precisión insuficiente | desde siempre |
| 572 coins con datos de julio entrando a los cálculos | hasta 78 días |
| Métricas de pares congeladas al salir de un umbral | hasta 20 días |
| Overflow rompiendo el sync, reportado como "executed successfully" | semanas |

**Ninguna la detectó el sistema. Todas aparecieron persiguiendo otra cosa.** Por
cada una que apareció, no sabemos cuántas quedan — no porque el código sea malo,
sino porque **nada verifica nada**.

### El cambio de premisa

| v2 | v3 |
|---|---|
| Obtener las coins de CoinGecko | **Gestionar** un universo de activos |
| Mostrar métricas en pantallas | **Responder preguntas** y sostener las respuestas |
| Pantallas que consultan datos | Un **motor** que alimenta al copiloto y al frontend |
| El trader interpreta lo que ve | El sistema **declara** qué mide, qué infiere y qué no sabe |

---

## 2. Qué es AXIOM v3

**Una plataforma de información, investigación, análisis y desarrollo sobre el
mercado cripto, con la que se conversa.**

Cuatro capas, y lo distintivo no es tenerlas: es que **la salida de una es la
entrada de la siguiente**.

```
INFORMACIÓN     el mercado está lateral con condiciones expansivas
      ↓
INVESTIGACIÓN   el capital rota hacia layer2
      ↓
ANÁLISIS        este par de layer2 oscila 8 % con spread 0,3 % y vuelve al origen
      ↓
DESARROLLO      esta estrategia se ajusta a eso — la activo
      ↓
      └────────→ y sus señales registradas vuelven al ANÁLISIS
```

Ninguna plataforma existente hace esa cadena. TradingView analiza pero no
investiga flujo; Glassnode investiga pero no diseña estrategias; Nansen informa
movimientos pero no dice qué hacer con un par concreto. Cada una cubre una capa.

Y el círculo se cierra en la cuarta: **una estrategia que registra sus señales
genera evidencia sobre qué funciona en qué condiciones**, y eso vuelve al
análisis. Ninguna plataforma lo hace porque ninguna deja crear la estrategia
adentro.

### El copiloto es el centro

No es una sección más. Las pantallas son vistas de lo que el sistema sabe; el
copiloto es la forma principal de preguntarle.

Y **lee y escribe**. Hasta ahora todas las capacidades eran de lectura; en v3 una
conversación puede producir algo que persiste y opera después: analizar un par,
diseñar una estrategia conversando, activarla, recibir notificaciones. Es una
diferencia de categoría, no de grado.

### El sistema NO opera

**Detecta condiciones y notifica. La operación la hace el trader.**

Es coherencia con el principio de siempre —AXIOM analiza, Migue decide— y baja
el riesgo un orden de magnitud: el peor caso de una estrategia mal diseñada es
una notificación equivocada, no una operación.

**Pero registra la operación completa.** Cada señal deja constancia de entrada,
stop, target y desenlace: si se alcanzó el objetivo, si saltó el stop, cuánto
tardó, cuánto rindió. Sin eso no hay forma de evaluar nada.

No es paper trading simulando operaciones ficticias: es el **registro de las
señales reales que la estrategia emitió**. Y cuando el trader opera, se compara
el resultado teórico con el real — ahí aparece la fricción verdadera: el hueco
entre la notificación y la ejecución, el deslizamiento, el precio que no se
alcanzó.

> **Salvedad declarada:** no todas las estrategias son notificables. Las que
> dependen de reaccionar en segundos —como comprar cuando se agota el mejor ask—
> no funcionan con un humano en el medio. Eso debe declararse en el catálogo, no
> descubrirse operando.

### Kepler deja de existir

Decisión firme: **el copiloto de skills es la evolución de Kepler, no su
complemento.** No conviven.

Consecuencia directa: quedan fuera `chat.py` (function calling), el orquestador
multi-agente, `chat_groq` y `agentes.py`. Hoy hay **cuatro interfaces
conversacionales** montadas en paralelo, tres de ellas experimentos superados, y
el sistema las mantiene y renombra a todas cada vez que algo cambia — el
renombre de `regimen_mercado` a `regimen_btc` tocó `agentes.py`, que solo existe
para el orquestador que ya nadie usa.

---

## 3. Cómo se usa

Tres modalidades, complementarias. No compiten: se alimentan.

| Modalidad | Cuándo | Qué pasa |
|---|---|---|
| **Preguntar** | hay una pregunta formada | el copiloto responde, con widgets si corresponden |
| **Explorar** | no hay pregunta formada, se quiere mirar | las secciones |
| **Acompañar** | se está mirando algo y surge la pregunta | se pregunta *desde* la sección, con contexto |

La tercera es la que ata las otras dos, y es la que hace que **las secciones no
compitan con el copiloto sino que lo alimenten**.

### El copiloto conoce el contexto

*"¿Cómo lo ves?"* no significa nada sin saber qué se está mirando. Con contexto,
el copiloto sabe que estás en Gráficos, con ROSE/BTC, en diario, con tal
indicador puesto.

**El contexto dice SOBRE QUÉ hablar, no CON QUÉ datos.** El copiloto usa sus
capacidades para traer lo que necesite; no queda limitado a lo que la pantalla
ya cargó. Si no, la respuesta valdría menos que la vista.

Y hay una pieza construida: `chart_state` y `chart_indicators` ya guardan qué
par se está mirando y con qué indicadores. Se hizo para otra cosa, pero es la
mitad del camino.

### El copiloto opera la aplicación

No solo responde dentro de su ventana. Puede:

- **navegar** — *"mostrame el gráfico de velas de ese par"*
- **actuar sobre los datos** — *"agregalo a la watchlist"*
- **operar la vista donde estás** — *"agregá una EMA de 21"*

Ese último caso es el más revelador: no lleva a otro lado ni cambia datos del
sistema, **cambia lo que la sección está haciendo en ese momento**. El vínculo
con la sección es bidireccional y en vivo.

Lo que implica: así como el sistema declara sus **capacidades**, tiene que
declarar sus **vistas** — qué existe, qué parámetros acepta, qué se le puede
pedir. El gráfico acepta indicadores, temporalidad, par; una tabla acepta orden
y filtros. El copiloto opera sobre eso declarativamente, sin conocer el JS de
cada pantalla. Es el mismo patrón que ya funciona con los widgets: **declarar en
el backend, renderizar en el frontend**.

Y si el estado de la vista es un dato, **el copiloto también lo lee**: sabe qué
hay en pantalla porque está guardado, no porque alguien se lo cuente.

### Qué necesita confirmación

La línea no está en si el copiloto escribe o no. Está en **si queda algo
funcionando por su cuenta después**.

- **Directo** — lo que se pidió y se deshace fácil: agregar a la watchlist,
  mostrar un gráfico, poner un indicador, crear una alerta. Pedir confirmación
  ahí sería preguntar si estás seguro de lo que acabás de decir.
- **Con confirmación** — activar una estrategia que va a empezar a notificar,
  borrar cosas con historia.

### La conversación tiene foco

*"Hablame de este par"* → *"agregalo a la watchlist"* → *"mostrame el gráfico"*.
El "lo" y el "me" refieren al mismo objeto sin nombrarlo.

Eso hoy no existe: cada consulta resuelve su target desde cero. v3 necesita un
**objeto en foco** que se establece y persiste hasta que cambie. Y se conecta
con lo anterior: el foco puede venir de lo que se está mirando o de lo que se
viene hablando. Son la misma idea desde dos lados.

### Secciones, widgets y vistas

Hoy "sección" mezcla tres cosas distintas:

- **una vista** — mostrar algo que el sistema sabe → eso ya son **widgets**
- **un espacio de trabajo** — Gráficos no es una vista: es donde se dibuja y se
  guarda estado. Bot tampoco: es donde se administran estrategias.
- **un punto de entrada** — *"quiero ver noticias"* necesita un lugar adónde ir

Se pueden desacoplar. Los widgets ya lo anticipan: declaran
`contextos=("pantalla","panel","chat","dashboard")` — **la misma vista
rindiéndose en cuatro lugares, incluido el chat**. Lo que sigue siendo sección
es el contenedor y la navegación, no el contenido.

**Este documento no decide cuántas secciones habrá.** Decide que el contenido es
componible y que el copiloto puede traerlo donde haga falta.

---

## 4. Qué tiene que poder responder

Las preguntas definen el sistema, no al revés. Lo que sigue no es exhaustivo, y
la expectativa explícita es que **se profundicen** a medida que el sistema crezca.

Marcas: ✅ hoy se puede · 🟡 el dato existe pero no es consultable ·
⏳ falta historia (solo tiempo) · ❌ falta fuente o modelo

### 4.1 Información

*El estado de las cosas. Sin interpretación, sin recomendación.*

**Estado general**
- ¿En qué régimen está Bitcoin? ✅
- ¿En qué régimen está el universo operable? ✅
- ¿Y el ecosistema de coins? ⏳
- ¿Cambió algo respecto de ayer, de la semana pasada? ⏳
- ¿Cuánto capital hay y cómo se reparte por sector? ✅

**Coins**
- ¿Qué es esta coin, qué hace, qué supply tiene? ✅
- ¿Cómo viene su precio, su volumen, su ranking? ✅
- ¿Dónde se puede operar y en qué mercados? ✅
- ¿Qué eventos tiene por delante? *(desbloqueos, upgrades)* ❌
- ¿Qué se está diciendo de ella? ✅

**Pares**
- ¿Qué pares hay para este activo y en qué exchanges? ✅
- ¿Cuánto se opera cada uno? ✅
- ¿Cuánto cuesta entrar y salir? ✅
- ¿Cuánto se mueve un día típico? ✅

**Contexto macro**
- ¿Cómo viene la dominancia de BTC y hacia dónde se mueve? 🟡
- ¿Cómo está el sentimiento del mercado? 🟡
- ¿Qué dicen los indicadores on-chain? 🟡
- ¿Cómo está el funding en derivados? 🟡
- ¿Cómo se comporta el cripto respecto de los mercados tradicionales? ❌

> Las cuatro 🟡 son señales del régimen que se guardan **cada hora desde el día
> 1** en `signal_readings` y solo se usan para votar. El dato está con 80 días
> de historia; falta exponerlo.

**Noticias**
- ¿Qué pasó hoy en el mercado? ✅
- ¿Qué se dice de esta coin? ✅

### 4.2 Investigación

*Buscar lo que no salta a la vista. No "cómo está X" sino "dónde hay algo".*

**Flujo de capital**
- ¿Hacia dónde se está moviendo el dinero? ⏳
- ¿Qué sectores ganan y pierden peso? ⏳
- ¿El movimiento es de muchas coins o de pocas grandes? ✅
- ¿Entra dinero nuevo o rota el que ya está? ❌

**Movimientos en el ranking**
- ¿Qué coins subieron o bajaron más puestos? ⏳
- ¿Qué entró y qué salió del top N? ⏳

**Actividad**
- ¿Qué pares se operan más de lo habitual? ✅
- ¿Dónde apareció volumen que antes no estaba? ⏳

**Ineficiencias** — *lo que ninguna plataforma hace*
- ¿Qué pares tienen spread desalineado con su liquidez real? 🟡
- ¿Dónde el precio se mueve barato? *(libro fino)* 🟡
- ¿Hay desajustes del mismo activo entre exchanges o entre quotes? ✅
- ¿Qué pares ofrecen más rango neto por unidad de fricción? ✅

**Candidatos**
- ¿Qué coins tienen condiciones favorables dadas? ⏳
- ¿Qué pares sirven para operar rangos? ✅

> Casi toda esta capa depende de **comparar contra el pasado**. Es la que más
> sufre la falta de historia y la que más va a mejorar sola con el tiempo.

### 4.3 Análisis

*Sobre un objeto concreto. Acá aparece la interpretación, siempre declarada.*

**Caracterización de un par**
- ¿Qué régimen describe? ¿Tendencia, rango, colapso? ✅
- ¿Cuánto se mueve y con qué repetibilidad? ✅
- ¿Ese movimiento es capturable o se lo come la fricción? ✅
- ¿Cómo se comporta su libro? ¿Aguanta tamaño? 🟡
- ¿Qué tan estable es todo esto en el tiempo? ⏳

**Comportamiento del par** — *estadística, no interpretación*
- ¿En qué franja horaria ocurre el máximo del día? ¿Y el mínimo? ❌
- ¿Con qué frecuencia el máximo llega antes que el mínimo? ❌
- ¿Cuántos días el precio vuelve al punto de partida? ✅
- ¿Hay días de la semana sistemáticamente distintos? ⏳
- ¿Cuánto tarda en recorrer su rango típico? ❌

> Categoría separada del análisis técnico a propósito: son **frecuencias
> medidas**, no lecturas. *"El 68 % de los días el mínimo ocurre antes del
> mediodía UTC"* se verifica contra su tasa base y dice directamente cuándo
> mirar. Además necesita **velas horarias, no ticks** — un salto de granularidad
> mucho más barato que capturar intradía completo.

**Análisis técnico**
- Estructura de precio, soportes y resistencias ❌
- ¿Dónde está respecto de su rango reciente? ✅
- ¿Hay niveles donde el precio reaccionó repetidamente? ❌

**Comparación**
- ¿Cómo se compara con otros pares similares? ✅
- ¿Le va mejor o peor que a su sector? ✅
- ¿Y respecto de BTC? ✅

**Aprovechamiento** — *el puente a desarrollo*
- ¿Cómo se puede aprovechar este movimiento? ❌
- ¿Qué estrategia se ajusta a estas características? ❌
- ¿Qué tamaño tolera sin mover el precio? 🟡

### 4.4 Desarrollo

*Donde el copiloto escribe.*

**Diseñar**
- Dado este par y su comportamiento, ¿qué estrategia se ajusta? ❌
- ¿Qué condiciones de entrada tienen sentido acá? ❌
- ¿Dónde poner el stop y el target según cómo se mueve? ❌
- ¿Esta idea que tengo es viable en este par? ❌

**Validar antes de activar**
- ¿Qué habría pasado en los últimos 60 días? ❌
- ¿Cuántas señales habría dado y con qué frecuencia? ❌
- ¿Es notificable, o necesita reaccionar más rápido de lo que puedo? ❌

**Activar y operar**
- Poner una estrategia a vigilar un par ❌
- Recibir la notificación cuando se cumplen las condiciones 🟡
- Registrar entrada, stop, target y desenlace de cada señal ❌
- Pausar, ajustar, desactivar ❌

**Evaluar** — *lo que cierra el círculo*
- ¿Cuántas señales dio y cuántas funcionaron? ❌
- ¿Cuánto rindió en teoría? ¿Y lo que efectivamente operé? ❌
- ¿Dónde está el hueco entre una cosa y la otra? ❌
- ¿En qué pares funciona y en cuáles no? ❌
- ¿Sigue funcionando o se degradó? ❌

> **La pregunta que ninguna otra plataforma puede responder:** *"¿qué estrategia
> funciona en pares con estas características?"* — no por teoría, sino por las
> propias señales medidas.

---

## 5. Los cuatro pilares

### 5.1 Datos gestionados, no obtenidos

Es el cambio de fondo. Un dato en v3 tiene que poder responder:

- **qué es** — qué mide exactamente, sobre qué universo, con qué método
- **cuándo** — hasta qué momento es válido
- **de dónde** — qué fuente, con qué límites conocidos
- **en qué estado está** — activo, inactivo, desde cuándo y por qué

Nada de eso es opcional cuando el consumidor es un modelo que razona.

Implica: **universo declarado** (qué existe, qué seguimos, con qué criterio),
**estado explícito** (un activo inactivo no se considera en ninguna capacidad,
garantizado por construcción y no por acordarse de filtrar), **frescura
declarada** por métrica, y **verificación automática** — que el sistema mida su
propia integridad y avise, en vez de revisarlo a mano cada tanto.

### 5.2 Capacidades componibles

Ya existe y funciona: el registro con `@capacidad`, la declaración
MIDE / INFIERE / NO SABE, los destilados con carriles separados para razonar y
para presentar. **Es lo mejor de v2 y es v3 anticipado.**

Lo que falta es que se **compongan**. Hoy cada pregunta nueva implicó una
capacidad nueva, un widget nuevo y un parche. Una arquitectura que admite
preguntas nuevas sin reescribirse tiene que permitir que el copiloto combine lo
que ya hay.

### 5.3 Estrategias como datos

Hoy una estrategia es código Python detrás de una `key`. Si el copiloto puede
crear una conversando, tiene que ser una **declaración**: condiciones,
parámetros, reglas de entrada, stop y target, que un motor interpreta.

Y esa misma declaración resuelve la pregunta *"¿qué estrategia se ajusta a este
par?"*: si las estrategias declaran qué condiciones necesitan —qué rango, qué
oscilación, qué spread toleran—, cruzarlas con las propiedades medidas del par
da la respuesta. **Las dos cosas salen del mismo diseño.**

De ahí ya tenemos la mitad medida: `rango_mediana_30d`, `oscilacion_30d`, la
curva de repetibilidad, `rango_neto`. Falta el otro lado de la ecuación.

### 5.4 Verificable por construcción

El sistema tiene que poder responder sobre sí mismo: qué jobs corren y qué
producen, qué datos están frescos, qué capacidades existen y cuáles se usan, qué
se actualiza y nadie consulta.

`job_runs` y el observador ya hacen parte de esto y ya encontraron cosas —un bot
muerto hacía dos meses, a las pocas horas de existir—. Es la dirección correcta,
incompleta.

---

## 6. Qué de v2 sirve

**Se conserva — es v3 anticipado**
- Registro de capacidades con declaración epistémica
- Destilados y separación razonamiento / presentación
- Widgets declarados en el backend
- `job_runs` y el observador
- Mediciones de la capa par: oscilación, curva de repetibilidad, rango neto,
  frescura de métricas
- Todo el método: hipótesis con regla de descarte escrita **antes** de mirar

**Se revisa — funciona, pero fue diseñado para otra premisa**
- Los syncs: hacen su trabajo, pero el universo es un residuo
- El modelo de datos de coins y pares
- Las siete secciones actuales

**Se cuestiona — puede no tener lugar**
- Lo que se actualiza y nadie consulta *(hay que inventariarlo: no lo sabemos)*
- Endpoints y tablas heredados de v1
- Capacidades que nadie invoca

**Se descarta — decidido**
- `chat.py` (Kepler con function calling): lo reemplaza el copiloto de skills
- `orquestador.py` (multi-agente): descartado por límites de tokens, sin tráfico
- `chat_groq.py`: superado por la migración a Gemini
- `agentes.py`: solo existe para el orquestador
- Las cuatro tablas del bot v1 —`bot_signals`, `bot_positions`, `bot_rules`,
  `bot_config`—: **cero lecturas** en todo el backend, medido sobre el código

---

## 7. Lo primero, y por qué

**Levantar el inventario de v2.** Qué existe, qué corre, qué produce, quién lo
consume.

No es una auditoría deprimente: es la única forma de que cualquier decisión
—conservar, refactorizar, reescribir— se tome con datos en vez de con
impresiones. Y es **medición, no construcción**: buena parte sale de `job_runs`,
del registro de capacidades y del esquema.

Puede que la conclusión sea que sobra la mitad. **Sería un buen resultado.**

### Lo que el inventario ya reveló (16/08/2026)

| Hallazgo | Dato |
|---|---|
| `ob_snapshots` es el **98 % de la base** | 3.941 MB de 4.030, para **2 pares** |
| Cuatro interfaces conversacionales montadas | tres son experimentos superados |
| Cuatro tablas del bot v1 sin lectores | medido sobre el código, no sobre tráfico |
| `alerts_job` corre **cada minuto** | para **2** alertas configuradas |
| `sync_spread_job` tarda 64 s por hora | 26 min/día — recién ahora se usa su dato |
| El capturador de `ob_snapshots` no está en `job_runs` | corre fuera del scheduler: **el observador no lo ve** |
| `strat_signals` tiene ~36.000 filas | con **una** estrategia declarada |
| 18 capacidades declaradas | el frontend usa 8 |

**Advertencia de método:** el tráfico de una semana **no sirve** para decidir
qué está muerto — refleja las sesiones de trabajo, no el uso real. Lo que se
sostiene arriba se apoya en el código y en la documentación del proyecto, no en
ausencia de llamadas.

Mientras tanto `coin_daily` sigue acumulando. Es lo único que no se puede apurar
y lo único que ya corre bien.

---

## 8. Lo que este documento NO decide

- La arquitectura: si se reescribe, se refactoriza o se migra por partes
- Cuántas secciones habrá y cuáles siguen siendo espacios de trabajo
- El criterio de seguimiento del universo
- Qué granularidad de datos se captura y para cuántos pares
- Cómo se declara una vista y qué parámetros expone cada una
- Cuándo, si alguna vez, el sistema pasa de notificar a operar

Todas dependen del inventario y del diseño que salga de acá. Decidirlas antes
sería repetir el error que trajo hasta este punto: **construir sobre supuestos en
vez de sobre lo medido.**

---

## Nota de método

Este documento existe porque el problema se descubrió persiguiendo tres coins con
variaciones absurdas. Al medir resultaron ser datos viejos; el problema de datos
viejos resultó ser de gestión del universo; y el de gestión del universo resultó
ser que **v2 nunca se pensó para lo que hoy hace**.

Es el mismo patrón que apareció con el umbral de volumen, con el bot v1 muerto y
con el sync perdiendo páginas: el síntoma visible era la punta de algo
estructural, y medir antes de arreglar lo hizo evidente.

La diferencia es que esta vez el síntoma no apuntaba a un bug sino a la premisa.
