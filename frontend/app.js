/* ═══════════════════════════════════════════════════════════════════════════
   AXIOM — frontend mínimo. Conversa con /api/copiloto, muestra la respuesta,
   los widgets que la respaldan y —protagonista— lo que cada dato no sabe.

   NOTA (enfoque B): los renderers de widget de acá son provisorios. De lo que
   necesiten para verse bien va a emerger QUÉ declara formalmente cada widget en
   el backend (el catálogo del escalón 2). Por ahora, el frontend define la
   necesidad; después se formaliza.
   ═══════════════════════════════════════════════════════════════════════════ */

const $conv = document.getElementById("conversacion");
const $form = document.getElementById("entrada");
const $input = document.getElementById("mensaje");
const $enviar = document.getElementById("enviar");
const $bienvenida = document.getElementById("bienvenida");

// ── Envío ────────────────────────────────────────────────────────────────────
$form.addEventListener("submit", (e) => {
  e.preventDefault();
  enviar();
});

function enviar() {
  const msg = $input.value.trim();
  if (msg) preguntar(msg);
}

// Textarea estilo chat: Enter envía, Shift+Enter hace salto de línea.
$input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    enviar();
  }
});

// Crece en altura con el contenido, hasta un máximo (y ahí scrollea).
function ajustarAlto() {
  $input.style.height = "auto";
  $input.style.height = Math.min($input.scrollHeight, 200) + "px";
}
$input.addEventListener("input", ajustarAlto);

document.querySelectorAll(".chip").forEach((c) =>
  c.addEventListener("click", () => preguntar(c.dataset.q))
);

async function preguntar(mensaje) {
  if ($bienvenida) $bienvenida.remove();
  $input.value = "";
  $input.style.height = "auto";
  $enviar.disabled = true;

  const $turno = document.createElement("section");
  $turno.className = "turno";
  $turno.innerHTML = `<div class="pregunta"></div>
                      <div class="respuesta pensando">pensando…</div>`;
  $turno.querySelector(".pregunta").textContent = mensaje;
  $conv.appendChild($turno);
  $conv.scrollTop = $conv.scrollHeight;

  try {
    const r = await fetch("/api/copiloto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje }),
    });
    if (!r.ok) {
      const detalle = await r.json().catch(() => ({}));
      throw new Error(detalle.detail || `error ${r.status}`);
    }
    const data = await r.json();
    pintarRespuesta($turno, data);
  } catch (err) {
    const $resp = $turno.querySelector(".respuesta");
    $resp.className = "error";
    $resp.textContent = err.message || "algo falló";
  } finally {
    $enviar.disabled = false;
    $input.focus();
    $conv.scrollTop = $conv.scrollHeight;
  }
}

// ── Pintado de una respuesta ──────────────────────────────────────────────────
function pintarRespuesta($turno, data) {
  const $resp = $turno.querySelector(".respuesta");
  $resp.className = "respuesta";
  $resp.textContent = data.texto || "(sin respuesta)";

  const material = (data.material || []).filter((m) => m.ok);
  if (material.length) {
    const $widgets = document.createElement("div");
    $widgets.className = "widgets";
    for (const m of material) $widgets.appendChild(widget(m));
    $turno.appendChild($widgets);
  }
}

$input.focus();

// ── Un widget por capacidad, renderizado POR TIPO de presentación ─────────────
// El frontend NO conoce capacidades concretas: renderiza según el `tipo` que la
// capacidad declara (serie_nivel/serie_flujo/comparacion/lista/reunion/ficha) y
// los `campos` que declara. Una capacidad nueva —o creada por el copiloto— se
// dibuja sola: declara su tipo y sus campos, y acá ya se sabe pintar.
function widget(m) {
  const $w = document.createElement("div");
  $w.className = "widget";

  const $t = document.createElement("div");
  $t.className = "widget-titulo";
  $t.textContent = m.titulo || m.capacidad;
  $w.appendChild($t);

  const pres = m.presentacion || {};
  const tipo = pres.tipo || "ficha";
  const render = RENDERERS_POR_TIPO[tipo] || renderFicha;
  $w.appendChild(render(m.valor || {}, pres.campos || []));

  // Sparkline: si el tipo lo lleva, se pide la serie on-demand y se dibuja sin
  // bloquear. (serie_nivel y serie_flujo tienen evolución temporal.)
  if (tipo === "serie_nivel" || tipo === "serie_flujo") {
    const $graf = document.createElement("div");
    $graf.className = "widget-spark";
    $w.appendChild($graf);
    cargarSparkline(m.capacidad, $graf);
  }

  if (m.no_sabe && m.no_sabe.length) {
    $w.appendChild(limites(m.no_sabe));
  }
  return $w;
}

// Sparkline SVG: la evolución de la serie con el punto actual marcado. Vanilla,
// sin dependencias. El panel de detalle (futuro) usará Lightweight Charts.
function sparkline(serie, {ancho = 260, alto = 48} = {}) {
  const vals = serie.map(p => p.valor);
  const min = Math.min(...vals), max = Math.max(...vals);
  const rango = (max - min) || 1;
  const pad = 4;
  const w = ancho - pad * 2, h = alto - pad * 2;
  const x = i => pad + (i / (serie.length - 1)) * w;
  const y = val => pad + h - ((val - min) / rango) * h;
  const puntos = serie.map((p, i) => `${x(i).toFixed(1)},${y(p.valor).toFixed(1)}`).join(" ");
  const ultimo = serie[serie.length - 1];
  const cx = x(serie.length - 1), cy = y(ultimo.valor);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
  svg.setAttribute("class", "spark");
  svg.setAttribute("width", ancho); svg.setAttribute("height", alto);
  const linea = document.createElementNS(ns, "polyline");
  linea.setAttribute("points", puntos);
  linea.setAttribute("fill", "none");
  linea.setAttribute("stroke", "var(--acento)");
  linea.setAttribute("stroke-width", "1.5");
  svg.appendChild(linea);
  const marca = document.createElementNS(ns, "circle");
  marca.setAttribute("cx", cx.toFixed(1)); marca.setAttribute("cy", cy.toFixed(1));
  marca.setAttribute("r", "3"); marca.setAttribute("fill", "var(--acento)");
  svg.appendChild(marca);
  return svg;
}

// Pide la presentación de una capacidad y, si trae serie, dibuja el sparkline.
async function cargarSparkline(nombre, $cont) {
  try {
    const r = await fetch(`/api/capacidad/${nombre}?para=presentacion`, {
      method: "POST", headers: {"Content-Type": "application/json"}, body: "{}",
    });
    if (!r.ok) return;
    const d = await r.json();
    const serie = (d.valor || {}).serie;
    if (!serie || serie.length < 2) return;
    $cont.appendChild(sparkline(serie, {ancho: 260, alto: 48}));
  } catch (e) { /* sin sparkline, el resumen ya está */ }
}

// ── Formato de un campo según su tipo declarado (conjunto cerrado) ────────────
const nf = (n, d = 2) => {
  if (n == null || n === "") return "—";
  const num = Number(n);
  if (Number.isNaN(num)) return String(n);
  return num.toLocaleString("es-AR", { maximumFractionDigits: d }).replace(/^-\s+/, "-");
};

const usd = (n) => {
  if (n == null) return "—";
  const a = Math.abs(Number(n));
  if (a >= 1e12) return `$${nf(n / 1e12, 2)} B`;
  if (a >= 1e9) return `$${nf(n / 1e9, 1)} MM`;
  if (a >= 1e6) return `$${nf(n / 1e6, 1)} M`;
  return `$${nf(n, 2)}`;
};

// Percentil → lectura (zona alta/baja) + clase de color.
function leerPercentil(p) {
  if (p == null) return { texto: "", clase: "" };
  const v = Number(p);
  if (v >= 70) return { texto: `percentil ${Math.round(v)} · zona alta`, clase: "alto" };
  if (v <= 30) return { texto: `percentil ${Math.round(v)} · zona baja`, clase: "medido" };
  return { texto: `percentil ${Math.round(v)} · normal`, clase: "" };
}

// snake_case / minúsculas → "Título legible".
function autoEtiqueta(clave) {
  return clave.replace(/_/g, " ").replace(/^\w/, c => c.toUpperCase());
}

// Heurística de formato cuando el campo no lo declara.
function formatoAuto(clave) {
  const k = clave.toLowerCase();
  if (k.includes("percentil")) return "pct_hist";
  if (k.includes("pct") || k.includes("porcentaje") || k.includes("dominancia")
      || k.includes("variacion")) return "pct";
  if (k.includes("cap") || k.includes("volumen") || k.includes("precio")
      || k.includes("usd") || k.includes("max_pain") || k.includes("spot")) return "usd";
  if (k.includes("fecha") || k === "desde" || k === "hasta") return "fecha";
  return "num";
}

// Renderiza UN campo (etiqueta + valor formateado) como una .metrica.
function campo(valor, spec) {
  const clave = spec.clave;
  const etiqueta = spec.etiqueta || autoEtiqueta(clave);
  const formato = spec.formato || formatoAuto(clave);
  const v = valor[clave];
  if (v == null) return null;

  let texto = "—", clase = "", contexto = "";
  switch (formato) {
    case "usd":  texto = usd(v); break;
    case "pct":  texto = `${nf(v, 2)}%`; break;
    case "pct_hist": {
      const l = leerPercentil(v); texto = String(Math.round(Number(v)));
      contexto = l.texto.replace(/^percentil \d+ · /, ""); clase = l.clase; break;
    }
    case "signo": {
      const num = Number(v); texto = `${num >= 0 ? "+" : ""}${nf(num, 2)}`;
      clase = num >= 0 ? "medido" : "alto"; break;
    }
    case "fecha": texto = String(v); break;
    case "texto": texto = String(v); break;
    default:      texto = nf(v);
  }
  return metrica(etiqueta, texto, { clase, contexto });
}

function metrica(etiqueta, valor, { clase = "", contexto = "" } = {}) {
  const $m = document.createElement("div");
  $m.className = "metrica";
  $m.innerHTML = `<span class="etiqueta"></span>
                  <span class="valor ${clase}"></span>
                  ${contexto ? '<span class="contexto"></span>' : ""}`;
  $m.querySelector(".etiqueta").textContent = etiqueta;
  $m.querySelector(".valor").textContent = valor;
  if (contexto) $m.querySelector(".contexto").textContent = contexto;
  return $m;
}

function rejilla(metricas) {
  const $g = document.createElement("div");
  $g.className = "metricas";
  metricas.forEach((m) => m && $g.appendChild(m));
  return $g;
}

// Los campos a mostrar: los declarados, o auto desde las claves escalares del
// valor (salteando internas y la serie).
function camposDe(valor, campos) {
  if (campos && campos.length) return campos;
  return Object.keys(valor)
    .filter(k => !k.startsWith("_") && k !== "serie"
                 && typeof valor[k] !== "object")
    .map(k => ({ clave: k }));
}

// ── Renderers POR TIPO (5 + ficha) ────────────────────────────────────────────
function renderSerieNivel(valor, campos) {
  return rejilla(camposDe(valor, campos).map(c => campo(valor, c)));
}

function renderSerieFlujo(valor, campos) {
  // Flujo: si hay sub-objetos (flujo / supply), aplana; si no, campos planos.
  if (valor.flujo || valor.supply_en_exchanges) {
    const ms = [];
    const f = valor.flujo, s = valor.supply_en_exchanges;
    if (f) {
      ms.push(metrica("Neto último día", `${f.neto_ultimo_dia >= 0 ? "+" : ""}${nf(f.neto_ultimo_dia)}`,
        { clase: f.neto_ultimo_dia >= 0 ? "medido" : "alto",
          contexto: `${f.racha_dias}d de ${f.racha_signo}` }));
      ms.push(metrica("Neto ventana", `${nf(f.neto_ventana)}`,
        { contexto: `${f.dias_ventana} días` }));
    }
    if (s) {
      const l = leerPercentil(s.percentil);
      ms.push(metrica("Supply en exchanges", nf(s.btc, 0),
        { clase: l.clase, contexto: l.texto }));
    }
    return rejilla(ms);
  }
  return renderSerieNivel(valor, campos);
}

function renderComparacion(valor, campos) {
  // Correlación: sub-objetos por serie (sp500, gold).
  const ms = [];
  for (const [k, v] of Object.entries(valor)) {
    if (typeof v !== "object" || v == null || k.startsWith("_")) continue;
    if (v.correlacion != null) {
      const l = leerPercentil(v.percentil);
      ms.push(metrica(autoEtiqueta(k), nf(v.correlacion, 2),
        { clase: l.clase, contexto: l.texto }));
    }
  }
  return ms.length ? rejilla(ms) : renderFicha(valor, campos);
}

function renderLista(valor, campos) {
  const $c = document.createElement("div");
  $c.className = "metricas";
  // Encabezado con el total si lo hay.
  if (valor.total_pares != null) {
    $c.appendChild(metrica("Pares activos", nf(valor.total_pares, 0),
      { contexto: (valor.exchanges || []).join(" · ") }));
  }
  const filas = valor.mercados || valor.items || valor.lista || [];
  filas.slice(0, 8).forEach(p => {
    $c.appendChild(metrica(p.simbolo || p.nombre || "—", p.exchange || p.valor || "",
      { contexto: p.minimo_orden ? `mín ${p.minimo_orden}` : "" }));
  });
  return $c;
}

function renderReunion(valor, campos) {
  // Compuesta anidada (btc_estado): cada componente es una sub-lectura.
  const dims = valor.dimensiones || valor;
  const ms = [];
  const recorrer = (obj, prefijo = "") => {
    for (const [k, v] of Object.entries(obj)) {
      if (k.startsWith("_") || k === "serie") continue;
      if (v && typeof v === "object") {
        if (v.dimensiones) { recorrer(v.dimensiones, ""); continue; }
        if (v.valor != null && v.percentil != null) {
          const l = leerPercentil(v.percentil);
          ms.push(metrica(autoEtiqueta(k.replace(/^btc_/, "")), nf(v.valor),
            { clase: l.clase, contexto: l.texto }));
        }
      }
    }
  };
  recorrer(dims);
  return ms.length ? rejilla(ms) : renderFicha(valor, campos);
}

// Piso: cualquier capacidad sin tipo declarado se ve decente (auto-etiquetas).
function renderFicha(valor, campos) {
  return rejilla(camposDe(valor, campos).map(c => campo(valor, c)));
}

const RENDERERS_POR_TIPO = {
  serie_nivel: renderSerieNivel,
  serie_flujo: renderSerieFlujo,
  comparacion: renderComparacion,
  lista: renderLista,
  reunion: renderReunion,
  ficha: renderFicha,
};

// ── La epistémica: colapsada tras una etiqueta que invita a abrirse ──────────
// El "no sé" es la identidad de AXIOM: la etiqueta (con ícono) siempre está,
// y al tocarla se despliegan todos los límites de la lectura.
function limites(noSabe) {
  const $d = document.createElement("details");
  $d.className = "limites";

  const $s = document.createElement("summary");
  $s.className = "limites-badge";
  $s.innerHTML = `<span class="limites-icono" aria-hidden="true"></span>
                  <span>Límites de esta lectura</span>`;
  $d.appendChild($s);

  const $ul = document.createElement("ul");
  noSabe.forEach((n) => {
    const $li = document.createElement("li");
    $li.textContent = n;
    $ul.appendChild($li);
  });
  $d.appendChild($ul);
  return $d;
}
