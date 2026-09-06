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

// ── Un widget por capacidad ───────────────────────────────────────────────────
function widget(m) {
  const $w = document.createElement("div");
  $w.className = "widget";

  const $t = document.createElement("div");
  $t.className = "widget-titulo";
  $t.textContent = TITULOS[m.capacidad] || m.capacidad;
  $w.appendChild($t);

  const render = RENDERERS[m.capacidad] || renderGenerico;
  $w.appendChild(render(m.valor));

  // La epistémica, desplegable, protagonista.
  if (m.no_sabe && m.no_sabe.length) {
    $w.appendChild(limites(m.no_sabe));
  }
  return $w;
}

const TITULOS = {
  btc_estado: "Estado de Bitcoin",
  btc_funding: "Funding de BTC",
  btc_opciones: "Opciones de BTC",
  mercado_dominancia: "Dominancia del mercado",
  coin_estado: "Estado de la coin",
  coin_mercados: "Dónde se opera",
  coin_historia: "Historia reciente",
};

// ── Renderers ─────────────────────────────────────────────────────────────────
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

// Traduce un percentil a su lectura y a una clase de color.
function leerPercentil(p) {
  if (p == null) return { texto: "", clase: "" };
  if (p >= 70) return { texto: `percentil ${Math.round(p)} · zona alta`, clase: "alto" };
  if (p <= 30) return { texto: `percentil ${Math.round(p)} · zona baja`, clase: "medido" };
  return { texto: `percentil ${Math.round(p)} · normal`, clase: "" };
}

const nf = (n, d = 2) => {
  if (n == null) return "—";
  // toLocaleString es-AR a veces mete un espacio raro tras el signo; se limpia.
  return Number(n)
    .toLocaleString("es-AR", { maximumFractionDigits: d })
    .replace(/^-\s+/, "-");
};

const usd = (n) => {
  if (n == null) return "—";
  const a = Math.abs(n);
  if (a >= 1e12) return `$${nf(n / 1e12, 2)} B`;
  if (a >= 1e9) return `$${nf(n / 1e9, 1)} MM`;
  if (a >= 1e6) return `$${nf(n / 1e6, 1)} M`;
  return `$${nf(n, 2)}`;
};

// btc_estado: compuesta anidada. Muestra las 5 dimensiones + funding + opciones + dominancia.
function renderBtcEstado(v) {
  const d = v.dimensiones || {};
  const perfil = (d.btc_perfil && d.btc_perfil.dimensiones) || {};
  const dim = (nombre, etiqueta) => {
    const x = perfil[nombre];
    if (!x) return null;
    const l = leerPercentil(x.percentil);
    return metrica(etiqueta, nf(x.valor), { clase: l.clase, contexto: l.texto });
  };
  const metricas = [
    dim("btc_direccion", "Dirección"),
    dim("btc_volatilidad", "Volatilidad"),
    dim("btc_estructura", "Estructura"),
    dim("btc_posicion", "Posición vs. máx"),
    dim("btc_participacion", "Participación"),
  ];
  const f = d.btc_funding;
  if (f) {
    const signo = f.tasa_actual > 0 ? "largos pagan" : "cortos pagan";
    metricas.push(metrica("Funding", `${nf(f.tasa_actual_pct, 4)}%`,
      { contexto: `${signo} · pct ${Math.round(f.percentil_actual * 100)}` }));
  }
  const o = d.btc_opciones;
  if (o) {
    metricas.push(metrica("Max-pain", usd(o.max_pain),
      { contexto: `${nf(o.distancia_max_pain_pct, 1)}% vs. spot` }));
    metricas.push(metrica("Put/Call", nf(o.put_call_oi, 2), { contexto: "por OI" }));
  }
  const dm = d.mercado_dominancia;
  if (dm) {
    metricas.push(metrica("Dominancia BTC", `${nf(dm.dominancia_btc, 1)}%`,
      { clase: "medido" }));
  }
  return rejilla(metricas);
}

function renderDominancia(v) {
  return rejilla([
    metrica("Dominancia BTC", `${nf(v.dominancia_btc, 1)}%`, { clase: "medido" }),
    metrica("Dominancia ETH", `${nf(v.dominancia_eth, 1)}%`),
    v.cambio_pp_ventana != null
      ? metrica("Cambio", `${nf(v.cambio_pp_ventana, 2)} pp`,
          { contexto: `en ${v.dias} días` })
      : null,
    metrica("Cap. total", usd(v.capitalizacion_total)),
    metrica("Volumen 24h", usd(v.volumen_total)),
    metrica("Coins activas", nf(v.coins_activas_fuente, 0)),
  ]);
}

function renderCoinEstado(v) {
  return rejilla([
    metrica("Precio", usd(v.precio)),
    metrica("Puesto", v.puesto != null ? `#${v.puesto}` : "—"),
    metrica("Cap.", usd(v.capitalizacion)),
    metrica("Volumen 24h", usd(v.volumen)),
    v.variacion_24h != null
      ? metrica("24h", `${nf(v.variacion_24h, 2)}%`,
          { clase: v.variacion_24h >= 0 ? "medido" : "alto" })
      : null,
    v.variacion_7d != null
      ? metrica("7d", `${nf(v.variacion_7d, 2)}%`,
          { clase: v.variacion_7d >= 0 ? "medido" : "alto" })
      : null,
  ]);
}

function renderCoinMercados(v) {
  const $c = document.createElement("div");
  $c.className = "metricas";
  $c.appendChild(metrica("Pares activos", nf(v.total_pares, 0),
    { contexto: (v.exchanges || []).join(" · ") }));
  // Lista compacta de los primeros pares
  (v.mercados || []).slice(0, 8).forEach((p) => {
    $c.appendChild(metrica(p.simbolo, p.exchange,
      { contexto: p.minimo_orden ? `mín ${p.minimo_orden}` : "" }));
  });
  return $c;
}

function renderCoinHistoria(v) {
  return rejilla([
    metrica("Cambio", v.cambio_pct != null ? `${nf(v.cambio_pct, 2)}%` : "—",
      { clase: (v.cambio_pct || 0) >= 0 ? "medido" : "alto",
        contexto: `${v.dias} días` }),
    metrica("Precio inicio", usd(v.precio_inicio)),
    metrica("Precio fin", usd(v.precio_fin)),
    v.puestos_ganados != null
      ? metrica("Puestos", v.puestos_ganados >= 0 ? `+${v.puestos_ganados}` : `${v.puestos_ganados}`,
          { contexto: "ganó/perdió" })
      : null,
  ]);
}

function renderFunding(v) {
  const signo = v.tasa_actual > 0 ? "largos pagan" : "cortos pagan";
  return rejilla([
    metrica("Tasa actual", `${nf(v.tasa_actual_pct, 4)}%`, { contexto: signo }),
    metrica("Percentil", Math.round(v.percentil_actual * 100),
      { contexto: "vs. su historia" }),
    metrica("Horas +", `${nf(v.horas_positivas_pct, 0)}%`,
      { contexto: `de ${v.horas}h` }),
  ]);
}

function renderOpciones(v) {
  return rejilla([
    metrica("Max-pain", usd(v.max_pain),
      { contexto: `${nf(v.distancia_max_pain_pct, 1)}% vs. spot` }),
    metrica("Put/Call", nf(v.put_call_oi, 2), { contexto: "por OI" }),
    metrica("OI total", nf(v.oi_total, 0)),
    metrica("Spot", usd(v.spot)),
  ]);
}

function renderGenerico(v) {
  // Fallback: muestra los pares clave→valor que sean escalares.
  const metricas = Object.entries(v)
    .filter(([k, val]) => typeof val !== "object" && !k.startsWith("_"))
    .slice(0, 8)
    .map(([k, val]) => metrica(k, typeof val === "number" ? nf(val) : String(val)));
  return rejilla(metricas);
}

const RENDERERS = {
  btc_estado: renderBtcEstado,
  mercado_dominancia: renderDominancia,
  coin_estado: renderCoinEstado,
  coin_mercados: renderCoinMercados,
  coin_historia: renderCoinHistoria,
  btc_funding: renderFunding,
  btc_opciones: renderOpciones,
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
