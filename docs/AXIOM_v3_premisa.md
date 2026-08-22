# AXIOM v3 — Premisa

> Escrito el 16/08/2026, después de reconocer que v3 no es una versión de v2
> sino otra cosa, y que seguir parchando v2 nos llevó al mismo lugar del que
> v2 había venido a sacarnos.

---

## 1. Por qué esto no es "v2 mejorada"

La v2 se pensó como **un cockpit que muestra datos de mercado**. Después
aparecieron Kepler y el copiloto, y el requisito de fondo cambió sin que nadie
reescribiera la premisa.

Un sistema que **muestra** datos y uno que **razona sobre** datos necesitan cosas
distintas. El primero tolera un dato viejo o ambiguo: vos lo mirás, lo
interpretás, lo descartás. El segundo lo toma como verdad y construye encima.

Eso explica por qué todos los problemas que aparecieron en la última semana son
del mismo tipo. No fueron errores de cálculo — fueron **datos que mentían en
silencio**:

| Encontrado | Cuánto llevaba |
|---|---|
| Bot v1 ejecutándose después de ser reemplazado, fallando cada 5 min | 2 meses |
| Sync perdiendo 250 coins por corrida (`continue` mal puesto) | semanas |
| Precios redondeados a cero por precisión insuficiente | desde siempre |
| 572 coins con datos de julio entrando a los cálculos | hasta 78 días |
| Métricas de pares congeladas al salir de un umbral | hasta 20 días |
| Overflow rompiendo el sync, reportado como "executed successfully" | semanas |

**Ninguna la detectó el sistema. Todas aparecieron persiguiendo otra cosa.**

Y ese es el dato que importa: por cada una que apareció, no sabemos cuántas
quedan. No porque el código sea malo, sino porque **nada verifica nada**.

### El cambio de premisa, dicho explícitamente

| v2 | v3 |
|---|---|
| Obtener las coins de CoinGecko | **Gestionar** un universo de activos |
| Mostrar métricas en pantallas | **Responder preguntas** y sostener las respuestas |
| Pantallas que consultan datos | Un **motor** que alimenta al copiloto y al frontend |
| El trader interpreta lo que ve | El sistema **declara** qué mide, qué infiere y qué no sabe |

---

## 2. Qué es AXIOM v3

**Un sistema con el que se conversa para analizar el mercado cripto, diseñar
estrategias y ser notificado cuando se cumplen sus condiciones.**

El copiloto es el centro, no una sección más. Las pantallas son vistas de lo que
el sistema sabe; el copiloto es la forma principal de preguntarle.

### El copiloto lee y escribe

Hasta ahora todas las capacidades eran de lectura. En v3 una conversación puede
**producir algo que persiste y opera después**:

- analizar un par con el copiloto
- diseñar o ajustar una estrategia para ese par, conversando
- activarla
- recibir notificaciones cuando sus condiciones se cumplen

Es una diferencia de categoría, no de grado, y condiciona toda la arquitectura.

### El sistema NO opera

**Detecta condiciones y notifica. La operación la hace el trader.**

No es una limitación temporal: es coherencia con el principio de siempre —AXIOM
analiza, Migue decide— y baja el riesgo un orden de magnitud. El peor caso de
una estrategia mal diseñada es una notificación equivocada, no una operación.

Y simplifica el diseño: sin ejecución no hay que gestionar saldos ni órdenes.

**Pero sí se registra la operación completa.** Cada señal deja constancia de
entrada, stop, target y desenlace: si se alcanzó el objetivo, si saltó el stop,
cuánto tardó, cuánto rindió. Sin eso no hay forma de evaluar nada.

No es paper trading simulando operaciones ficticias: es **el registro de las
señales reales que la estrategia emitió**. Y cuando el trader opera, se puede
comparar el resultado teórico con el real — ahí aparece la fricción verdadera:
el hueco entre la notificación y la ejecución, el deslizamiento, el precio que
no se alcanzó.

Eso convierte al sistema en algo que **aprende de sus propias señales**.

> **Salvedad declarada:** no todas las estrategias son notificables. Las que
> dependen de reaccionar en segundos —como la del libro de órdenes, comprar
> cuando se agota el mejor ask— no funcionan con un humano en el medio. Eso
> debe declararse en el catálogo, no descubrirse operando.

---

## 3. Qué tiene que poder responder

Las preguntas definen el sistema, no al revés. Estas son de referencia, no
exhaustivas — y la expectativa explícita es que **se vuelvan más profundas** a
medida que el sistema crezca.

| # | Pregunta | Qué exige |
|---|---|---|
| 1 | Las tres coins que más subieron/bajaron en el ranking | **historia** del ranking |
| 2 | Cuáles son los pares más operados en MEXC/CoinEx | ✅ ya se puede |
| 3 | Qué par o coin tiene mayor potencial de subida | modelo **declarado** + tasa base medida |
| 4 | Cómo está fluyendo el dinero en el mercado | **historia** de sectores y volumen |
| 5 | Análisis técnico de un par | datos **intradía** |
| 6 | Info de una coin: por ejemplo, cuándo hay desbloqueo de monedas | **fuente nueva** |
| 7 | Quiero tradear este par, ¿qué estrategia se ajusta? | **catálogo declarativo** de estrategias |

### Lo que revelan

**De las siete, hoy se responde una.** No por falta de código —hay muchísimo—
sino porque faltan cuatro cosas distintas:

1. **Historia.** Las preguntas 1 y 4 no son un problema de programación sino de
   tiempo: `coin_daily` empezó el 13/08/2026. En 30 días se responde "del mes".
   Nada las acelera. Por eso era el único frente que sangraba.

2. **Datos que no capturamos.** Desbloqueos (pregunta 6) e intradía (5) son
   integraciones nuevas, no ajustes. El desbloqueo es especialmente valioso: es
   un evento con **fecha conocida de antemano**.

3. **Modelos declarados.** La 3 y la 7 no se contestan con más datos sino con
   criterios explícitos. Y la 3 tiene un riesgo: "potencial de subida" es una
   predicción. Se responde honestamente reformulándola —qué pares están en
   condiciones históricamente asociadas a movimientos al alza, con la tasa base
   medida— pero si la respuesta es un ranking de "estas van a subir", el sistema
   dejó de analizar y empezó a pronosticar.

4. **Composición.** Varias exigen combinar capacidades que hoy no se hablan.

**Y ninguna es una pantalla.** Todas son preguntas a un sistema que sabe cosas.

---

## 4. Los cuatro pilares

### 4.1 Datos gestionados, no obtenidos

Es el cambio de fondo. Un dato en v3 tiene que poder responder:

- **qué es** — qué mide exactamente, sobre qué universo, con qué método
- **cuándo** — hasta qué momento es válido
- **de dónde** — qué fuente, con qué límites conocidos
- **en qué estado está** — activo, inactivo, desde cuándo y por qué

Nada de eso es opcional cuando el consumidor es un modelo que razona.

Lo que implica:

- **Universo declarado**: qué existe, qué seguimos, con qué criterio y desde
  cuándo. No un residuo de `per_page × páginas`.
- **Estado explícito**: activo/inactivo con fecha y motivo. Un activo inactivo
  **no se considera en ninguna capacidad** — garantizado por construcción, no
  por acordarse de filtrar en cada consulta.
- **Frescura declarada**: cada métrica dice hasta cuándo vale.
- **Verificación automática**: el sistema mide su propia integridad y registra
  el resultado. No revisar a mano cada tanto — que el sistema avise.

### 4.2 Capacidades componibles

Ya existe y funciona: el registro con `@capacidad`, la declaración
MIDE/INFIERE/NO SABE, los destilados. **Es lo mejor de v2 y es v3 anticipado.**

Lo que falta es que se compongan. Hoy cada pregunta nueva implicó una capacidad
nueva. Una arquitectura que admite preguntas nuevas sin reescribirse tiene que
permitir que el copiloto **combine** lo que hay.

### 4.3 Estrategias como datos

Hoy una estrategia es código Python detrás de una `key`. Si el copiloto puede
crear una conversando, tiene que ser una **declaración**: condiciones,
parámetros, reglas de entrada, stop y target, que un motor interpreta.

Y esa misma declaración resuelve la pregunta 7: si las estrategias declaran qué
condiciones necesitan —qué rango, qué oscilación, qué spread toleran—, cruzarlas
con las propiedades medidas de un par responde "cuál se ajusta". Las dos cosas
salen del mismo diseño.

De ahí ya tenemos la mitad medida: `rango_mediana_30d`, `oscilacion_30d`, la
curva de repetibilidad, `rango_neto`. Falta el otro lado de la ecuación.

### 4.4 Verificable por construcción

El sistema tiene que poder responder sobre sí mismo: qué jobs corren y qué
producen, qué datos están frescos, qué capacidades existen y cuáles se usan, qué
se actualiza y nadie consulta.

`job_runs` y el observador ya hacen parte de esto y ya encontraron cosas. Es la
dirección correcta, incompleta.

---

## 5. Qué de v2 sirve

Más de lo que parecía al empezar esta conversación. Vale distinguir tres cosas:

**Se conserva — es v3 anticipado**
- El registro de capacidades con declaración epistémica
- Los destilados y la separación razonamiento/presentación
- El sistema de widgets declarados en backend
- `job_runs` y el observador
- Las mediciones de la capa par: oscilación, curva de repetibilidad, rango neto
- Todo el método: hipótesis con regla de descarte escrita antes de mirar

**Se revisa — funciona pero fue diseñado para otra premisa**
- Los syncs: hacen su trabajo, pero el universo es un residuo
- El modelo de datos de coins y pares
- Las siete secciones actuales

**Se cuestiona — puede no tener lugar**
- Lo que se actualiza y nadie consulta *(hay que inventariarlo: no lo sabemos)*
- Endpoints y tablas heredados de v1
- Capacidades que nadie invoca

---

## 6. Lo primero, y por qué

**Levantar el inventario de v2.** Qué existe, qué corre, qué produce, quién lo
consume.

No es una auditoría deprimente: es la única forma de que cualquier decisión
—conservar, refactorizar, reescribir— se tome con datos en vez de con
impresiones. Y es medición, no construcción: buena parte sale de `job_runs`, del
registro de capacidades y del esquema.

Puede que la conclusión sea que sobra la mitad. **Sería un buen resultado.**

Mientras tanto, `coin_daily` sigue acumulando. Es lo único que no se puede
apurar y lo único que ya está corriendo bien.

---

## 7. Lo que este documento NO decide

- La arquitectura técnica: si se reescribe, se refactoriza o se migra por partes
- Si siguen siendo siete secciones
- Cuál de las dos interfaces conversacionales sobrevive (`chat.py` con function
  calling, `copiloto_skills.py` con intenciones) o si se unifican
- El criterio de seguimiento del universo
- Cuándo, si alguna vez, el sistema pasa de notificar a operar

Todas dependen del inventario. Decidirlas antes sería repetir el error que trajo
hasta acá: **construir sobre supuestos en vez de sobre lo medido.**

---

## Nota de método

Esta premisa existe porque el problema se descubrió persiguiendo tres coins con
variaciones absurdas. Al medir resultaron ser datos viejos, el problema de datos
viejos resultó ser de gestión del universo, y el de gestión del universo resultó
ser que v2 nunca se pensó para lo que hoy hace.

Es el mismo patrón que apareció con el umbral de volumen, con el bot v1 muerto y
con el sync perdiendo páginas: **el síntoma visible era la punta de algo
estructural**, y medir antes de arreglar lo hizo evidente.

La diferencia es que esta vez el síntoma no apuntaba a un bug sino a la premisa.
