# AXIOM v3 — Copiloto basado en SKILLS · Estado y decisiones

> Documento de traspaso entre sesiones. Si estás retomando AXIOM v3 en un chat
> nuevo, **leé esto primero**. Captura las decisiones, la arquitectura, qué está
> hecho, qué falta y las lecciones de método de la sesión donde se diseñó el
> enfoque de skills. El código está en el repo; este doc es el *por qué*.

---

## 1. El giro central: de AGENTES a SKILLS

Durante varias sesiones se construyó un enfoque **multi-agente**: cinco agentes
(mercado, coin, pares, técnico, noticias), cada uno un LLM con tool-calling que
decidía qué capacidades llamar en un loop. **Ese enfoque se abandonó.** No por
capricho: falló estructuralmente.

**Por qué falló (medido, no supuesto):** el loop de tool-calling hacía que el LLM
recibiera los resultados crudos de las capacidades en su contexto. Una capacidad
(`top_coins`) devuelve el ranking entero de coins = **~89.000 tokens**. Con el
límite de 8.000 TPM de `gpt-oss-120b` en free tier, el request explotaba
(`context_length_exceeded` / 413). Fallaba ~10 de 11 veces y tardaba 45-94s.

**La decisión (la tomó Migue):** no necesitamos agentes, necesitamos **skills**.
La diferencia:
- Un **agente** es un LLM con autonomía que decide y ejecuta en un loop.
- Una **skill** es una función de código que hace una cosa concreta y devuelve un
  resultado acotado. No decide, no habla con un LLM. Es código determinista.

**Las capacidades del registro YA SON las skills.** Los agentes eran andamiaje
innecesario alrededor de ellas.

**El principio** (confirmado por un documento sobre arquitecturas de chatbots de
producción que Migue trajo, tipo LangGraph/máquina de estados): en producción
real, **el código orquesta y el LLM es solo un nodo que entiende y redacta**. No
un cerebro autónomo tragando datos crudos en loops.

---

## 2. La arquitectura de skills (el flujo)

Endpoint: `/api/experimental/copiloto-skills` (archivo `backend/api/copiloto_skills.py`).
Aislado, no toca producción (Kepler-Gemini) ni el orquestador de agentes viejo.

Cuatro etapas, **una sola llamada al LLM** (al final):

1. **CLASIFICAR** (código, patrones regex, sin LLM). El texto → intención.
   "contame de X" → `analisis_coin`. Mapa `_INTENCIONES`: cada intención declara
   sus patrones y qué skills dispara. Determinista (decisión de Migue: opción 1,
   sin LLM decidiendo, más predecible).

2. **RESOLVER TARGET** (código). Extrae el símbolo/nombre del mensaje y lo
   resuelve a `coin_id` vía tabla `coins` (por símbolo exacto, luego por nombre).

3. **EJECUTAR + DESTILAR SKILLS** (código, en paralelo con `asyncio.gather`). El
   código llama las skills (funciones normales, cero LLM) y **destila** cada
   resultado a su esencia. Acá se resuelve `top_coins`: el código extrae lo
   relevante, el LLM nunca ve el crudo.

4. **REDACTAR** (1 llamada LLM). Recibe el material destilado y redacta con la
   disciplina epistémica. Sin loop, sin tool-calling, sin datasets crudos.

**Resultado medido:** 1 llamada LLM, ~5 segundos, **cero errores de contexto**.
Contra los agentes: 5-6 llamadas, 45-94s, fallo casi siempre.

---

## 3. El DESTILADO (el corazón del diseño)

Migue identificó que **el éxito del sistema está en cómo se diseñan las skills:
qué destila cada una y para qué**. El destilado es la reducción del resultado
crudo a la "lectura esencial" que va al razonamiento.

**Decisión: el destilado es FIJO por skill** (no varía según la pregunta). Cada
capacidad sabe cuál es su esencia y siempre extrae lo mismo. Es una propiedad de
la capacidad, declarada en el registro junto a `mide`/`infiere`.

**Cómo se declara** (campo `destila` en el decorador `@capacidad`, en
`registry.py`). Soporta **ambas** formas (decisión de Migue):
- **Lista de campos**: `destila=("metadata_mercado", "regimen_relativo")` — se
  queda con esos campos (y les quita los de `presentacion` anidados). Simple.
- **Función**: `destila=<callable>` — transforma. Necesaria para casos como
  `top_coins`: una función que de 3000 coins extrae "el puesto de la coin X".
  Puede recibir `(resultado)` o `(resultado, contexto)`, donde contexto lleva
  p.ej. `{"coin_id": "ontology"}`.

**Jerarquía** (método `registro.destilar(nombre, resultado, contexto)`):
función > lista de campos > genérico (quita presentación + trunca listas >15).

**Estado:** solo `analizar_coin` tiene su destilado declarado
(`destila=("metadata_mercado","regimen_relativo")`, validado por Migue como su
esencia: números clave + las 3 lecturas). Las otras 13 caen al genérico.

**Relación con `presentacion`:** campo aparte, también declarado por capacidad.
`presentacion=("sparkline","image")` marca los datos-de-MOSTRAR (van al frontend,
no al razonamiento). `analizar_coin` lo declara. Los dos carriles: datos crudos
de presentación → frontend/widgets; destilado → razonador.

---

## 4. Disciplina epistémica de TRES carriles

AXIOM ya distinguía **MIDE** (hecho) / **INFIERE** (lectura). En esta sesión se
extendió a un tercer origen, para el conocimiento del propio modelo.

El insight (de Migue): el LLM tiene conocimiento de su entrenamiento; cuando
menciona algo que no está en los datos de AXIOM (ej. un nivel de precio
histórico), no necesariamente inventa — puede estar aportando de su conocimiento.
**La solución no es limitarlo, es exigir que declare el origen.**

Los tres carriles (instruidos en el prompt del redactor, `_REDACTOR_SYSTEM`):
- **[MEDIDO]**: dato que está literalmente en el material de AXIOM. Hecho.
- **[INFERIDO]**: lectura del modelo sobre lo medido. Marcado con "sugiere",
  "indica", "el perfil apunta a".
- **[APORTADO]**: conocimiento propio del modelo, NO de AXIOM. Debe declararlo
  explícitamente y con cautela ("según mi conocimiento general, puede estar
  desactualizado"), porque tiene fecha de corte.

**Regla crítica añadida:** solo se etiqueta [MEDIDO] lo que está literalmente en
el material. Prohibido inventar fechas/cifras/precios que no estén. (Se agregó
tras ver al modelo inventar una fecha de captura una vez.)

**Validado en vivo:** el modelo etiqueta bien los tres orígenes, y hasta hace algo
sofisticado — cuando su conocimiento (ONT ~0.3-0.7 USD, corte 2024) discrepa del
dato de AXIOM (ATL 0.036 en jul-2026), **marca la discrepancia y sugiere
verificar** en vez de elegir uno. Humildad epistémica funcionando.

---

## 5. Estado del código (qué está hecho)

**Commiteado y pusheado** (commit `393b429`):
- `backend/api/copiloto_skills.py` — el copiloto de skills completo (4 etapas).
  Intención `analisis_coin` funcionando end-to-end. Prompt con 3 carriles.
- `backend/domain/registry.py` — campos `presentacion` y `destila` en la clase
  `Capacidad`; métodos `presentacion_de()` y `destilar()`; decorador los acepta.
- `backend/domain/coin.py` — `analizar_coin` declara `presentacion` y `destila`.
- `backend/main.py` — router registrado (commit previo).

**Sin commitear / aislado:**
- `backend/api/orquestador.py` — el orquestador de AGENTES (enfoque viejo). Tiene
  instrumentación temporal `[MEDICION]` y quedó fuera del commit. Deprecado en
  favor de skills, pero sigue ahí por si se quiere consultar.
- `backend/domain/agentes.py` — declaración de los 5 agentes + registro. Del
  enfoque viejo. También sin commitear (o en commit WIP anterior).

**Stack sin cambios:** Python 3.11 + FastAPI (8002) + PostgreSQL 17 (`axiom_v2`,
user `axiom_user`) + asyncpg. Server `decentralia` (192.168.0.88), systemd
`axiom-v2.service`. Modelo LLM: `openai/gpt-oss-120b` en Groq (free tier, 8k TPM
— este límite fue la causa raíz de todo). venv: `/home/migue/apps/axiom-v2/venv`.

---

## 6. Qué falta (frentes abiertos)

En orden de valor, entrelazados (agregar una intención requiere diseñar los
destilados de sus skills):

1. **Más intenciones.** Hoy solo `analisis_coin` ("contame de X"). Faltan:
   "cómo está el mercado" (dispara top_coins/regimen_mercado/mapa_sectores),
   "precio de X", "noticias de X". Cada una: entrada en `_INTENCIONES` + destilados.

2. **Destilados de las otras 13 capacidades.** El trabajo de diseño fino. El más
   urgente es `top_coins` (necesita función de destilado que extraiga "el puesto
   de X" o "top N", NO el genérico que truncaría mal 3000 coins). Sin esto, la
   intención "cómo está el mercado" volvería a explotar.

3. **Carril de presentación al frontend.** Hoy el destilado saca los datos de
   presentación pero no se usan — el copiloto *menciona* el gráfico pero no lo
   *muestra*. Falta conectar los datos crudos (sparkline, velas) al frontend para
   renderizar widgets. Reusar la filosofía de widgets de AXIOM v2. El modelo ya
   "pide ver el gráfico" en sus respuestas — cerrar ese círculo.

4. **Limpieza:** quitar la instrumentación `[MEDICION]` de `orquestador.py`, o
   deprecar formalmente el enfoque de agentes. Y las etiquetas [MEDIDO]/[INFERIDO]
   /[APORTADO] son toscas visualmente (corchetes en mayúscula) — cosmética para
   cuando se diseñe la presentación real (quizás agrupar por origen en vez de
   etiquetar oración por oración).

**Pendiente de comportamiento (menor):** el texto a veces se acerca al límite de
tokens (`max_tokens=1700`). Vigilado, no bloqueante.

---

## 7. Lecciones de MÉTODO (importantes, se ganaron a los golpes)

Estas lecciones valen tanto como el código. Migue las impuso al ritmo de trabajo:

- **Medir antes de decidir.** Se perdieron horas diagnosticando causas
  equivocadas con exceso de confianza (yo, el asistente, me apuré varias veces).
  El problema real (`top_coins` = 89k tokens) sólo apareció cuando se instrumentó
  y se midió el request, en vez de suponer. **Una hipótesis, una medición, un
  cambio, un commit.** No apilar parches.

- **No atarse a lo construido.** El giro de agentes→skills salió de que Migue
  preguntó "¿por qué atarnos a widgets/agentes/capacidades?". El apego a lo hecho
  es enemigo del buen diseño. Estar dispuesto a tirar andamiaje.

- **No parchar el síntoma.** La poda de sparklines, la "secretaria consolidadora"
  — todas movían el problema de lugar sin resolverlo. Migue detectó cada vez que
  una solución era un parche. La solución real ataca la causa (el LLM no debe
  recibir datos crudos, punto).

- **Commitear los puntos estables.** No haber commiteado versiones intermedias
  causó una confusión grande de versiones (había que reconstruir "la versión de
  los guiones" de memoria). Ahora: commit en cada hito.

- **Los adjuntos .txt a veces llegan vacíos** al asistente. Si pasa, pegar el
  texto directo en el chat o usar `grep`/`cat` y pegar la salida.

- **Verificar el estado real del server, no suponerlo.** `grep` en los archivos
  del server dice qué está corriendo; no confiar en la memoria de qué se subió.

---

## 7b. Capacidades de POSICIONAMIENTO (Deribit) — funding + opciones

Archivo: `backend/dominio/posicionamiento.py`. Enganchado en `backend/app.py`
(import + `dominio_posicionamiento.declarar()` junto a las otras). Dos
capacidades INDIVIDUAL sobre `Objeto.MERCADO`, vigencia `cierre_vela_diaria`.
Son de **BTC-la-referencia** (posicionamiento agregado del mercado), no de un
par operable — misma distinción que `btc_recorrido_oculto`.

**`btc_funding`** — lee `funding_btc` (Deribit, perpetuo inverso, horario desde
2020). Devuelve la última tasa, su percentil dentro de la ventana (default 30
días), mediana, y % de horas positivas. **Todo en FRACCIÓN**; el % se agrega
sólo para mostrar, en campos aparte (`*_pct`). Respeta la lección de la tabla:
un umbral en % comparado contra fracción es 100× de error. Salió sana al primer
intento.

**`btc_opciones`** — lee `opcion_diaria` (una fila por opción por día). Dos
planos que NO se mezclan:
- **Agregado (contexto):** put/call por OI, OI total, spot. Sobre todos los
  vencimientos.
- **Max-pain de corto/medio plazo:** el strike de menor dolor total, calculado
  sólo sobre vencimientos hasta el trimestral cercano inclusive.

### La cadena de correcciones (esto es la lección, no el resultado)

El primer diseño reportaba "el strike de mayor OI (el muro)" sobre **todos** los
vencimientos. Dio 70.000 a −11% del spot. **Ambiguo → se midió antes de
aceptarlo.** El top-8 de strikes mostró que 70k no dominaba (28k vs 21k del
segundo), y que ese OI venía sumado sobre 12 vencimientos. El "muro" era
**sedimento de calendario**: mezclaba el trimestral de diciembre con el diario
de mañana como si pesaran igual.

- **Corrección 1 — corte por vencimiento.** Restringir el cálculo a los
  vencimientos cercanos. Primer intento de detección: "primer vencimiento en mes
  trimestral (3/6/9/12)". **Bug medido:** matcheó el diario del 1-sep (mes 9),
  no el trimestral del 25-sep. `muro_hasta_venc` salió `2026-09-01` y el OI del
  muro era 426 (ridículo) → delató el error.
- **Corrección 2 — detectar el trimestral por su OI.** Los datos mostraron que
  todos los vencimientos son viernes (DOW=5), así que "último viernes" no
  discrimina; hay 4 viernes en septiembre. Lo que SÍ define al trimestral es su
  **tamaño**: 25-sep = 164k OI contra 28k del segundo. Detección final: el
  vencimiento de mayor OI del primer mes trimestral presente. Robusto, sin
  reglas de calendario frágiles.
- **Corrección 3 — de "muro" a max-pain.** Migue preguntó: "¿por qué no hacemos
  lo que hace Deribit?". Se verificó la API: **Deribit NO sirve max-pain ni el
  muro como endpoint** — sólo da los datos crudos por instrumento (OI, IV,
  greeks, mark) que ya capturamos. Lo que su web muestra son cálculos sobre esos
  datos. Así que "hacer lo que hace Deribit" = calcular **max-pain** (su métrica,
  el imán del precio), no inventar un "strike de mayor OI" que era una tercera
  métrica más pobre que no correspondía a nada que la fuente mostrara.

Max-pain final: **72.000 a −9.38% del spot** (79.454). No coincidió con el muro
(70k) — son métricas distintas, y probarlo con datos reales (no con el set de
prueba, que daba 70k) lo confirmó. Lectura de fondo sostenida: el posicionamiento
en opciones está anclado ~9% por debajo del spot.

### Sub-lecciones de esta sesión

- **El caché vive en la tabla `valores`, no sólo en memoria.** Un `systemctl
  restart` carga el código nuevo pero NO fuerza recálculo: las capacidades
  cuelgan de `cierre_vela_diaria` y sólo recalculan al cierre. Tras deployar un
  cambio de cálculo, hay que invalidar la fila:
  `DELETE FROM valores WHERE capacidad = '<nombre>';` y volver a pedirla.
  Señal de que estás viendo caché viejo: `desde_cache: true` + campos que ya no
  existen en el código.
- **La clave de caché es `capacidad` + `objeto_id` + `args`.** NO incluye el
  nombre en `objeto_id`. Todas las capacidades de mercado comparten
  `objeto='mercado'`, `objeto_id='mercado'`, `args={}`; las distingue la columna
  `capacidad`. Un DELETE debe filtrar por `capacidad` para no arrasar el caché
  de las demás.
- **Max-pain** = el strike K que minimiza el valor intrínseco total si todo
  expirara en K (calls con strike<K + puts con strike>K, ponderado por OI).
  Calculado en Python puro sobre los strikes del corte. Pondera por distancia →
  sensible a strikes extremos con mucho OI. Declarado en el `no_sabe`: es una
  regularidad discutida, no una ley.

---

## 8. Cómo retomar

1. Leé este doc.
2. Mirá el código en el repo: `copiloto_skills.py` (el flujo), `registry.py`
   (destila/presentacion), `coin.py` (ejemplo de destilado declarado).
3. Probá que anda: `curl -s -X POST http://localhost:8002/api/experimental/copiloto-skills -H "Content-Type: application/json" -d '{"mensaje":"contame de ONT"}'`
4. Elegí frente (sección 6). El camino natural: agregar "cómo está el mercado"
   diseñando de paso el destilado-función de `top_coins`.
