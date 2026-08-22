# AXIOM v3

Plataforma de información, investigación, análisis y desarrollo sobre el mercado
cripto, con la que se conversa.

> **v3 no se construye sobre v2.** v2 es referencia —enseñó qué funciona y qué
> no— pero no es la base. Historia desde cero.

## Documentos

| Documento | Qué define |
|---|---|
| `docs/AXIOM_v3_fundacional.md` | qué es AXIOM, las cuatro capas, el modelo de interacción |
| `docs/AXIOM_v3_arquitectura.md` | capacidades, operaciones, vocabulario, modelo de cálculo |
| `docs/AXIOM_v3_declaraciones.md` | cómo se declara cada pieza |

## Estructura

```
backend/
  fuentes/     de dónde vienen los datos — UNA implementación de "pedir"
  nucleo/      el motor: capacidades, operaciones, vigencia
  captura/     los jobs que acumulan historia
  modelo/      el vocabulario y la persistencia
declaraciones/ las capacidades y fuentes como DATO
migrations/    esquema de la base
```

## Estado

Punto 1 del plan: **fuentes y captura**. Funcionando.

```
backend/fuentes/cliente.py       UNA implementación de "pedir a una API"
backend/fuentes/coingecko.py     la declaración, con sus límites MEDIDOS
backend/nucleo/bus.py            eventos: quien publica no sabe quién escucha
backend/nucleo/planificador.py   lo único que sabe CUÁNDO
backend/captura/universo.py      inventariar · refrescar · fotografiar
backend/app.py                   el único lugar donde se conecta todo
```

### Cómo corre

```bash
# a mano
venv/bin/python scripts/capturar.py todo
venv/bin/python scripts/salud.py --historial 10

# como servicio (API + captura en el mismo proceso, puerto 8003)
sudo cp axiom-v3.service /etc/systemd/system/
sudo systemctl enable --now axiom-v3
```

### La API

Pocas rutas escritas a mano: casi todo se expone por **una ruta genérica** que
resuelve cualquier capacidad del registro. Agregar una capacidad no requiere
endpoint nuevo.

| Ruta | Qué |
|---|---|
| `POST /api/capacidad/{nombre}` | resuelve cualquier capacidad declarada |
| `GET /api/capacidades` | el catálogo: qué existe y qué declara cada una |
| `GET /api/sistema/estado` | universo, planificador, bus, salud |
| `GET /api/sistema/ejecuciones` | historial: qué corrió, por qué, qué devolvió |
| `GET /api/sistema/fuentes` | fuentes con sus límites y qué ofrece cada una |
| `GET /docs` | documentación automática |

> v2 tenía 18 routers montados a mano y nadie tenía la lista completa: el
> inventario encontró tres bajo el mismo prefijo, uno sin una sola llamada en
> siete días.

### Lo que hace solo

| Cuándo | Qué |
|---|---|
| cada 6 h | refresca precio, capitalización y ranking |
| 01:00 UTC | inventario completo — detecta altas y bajas |
| al cerrar el día UTC | **por evento**: la foto diaria del día que cerró |

### Medido, no supuesto

CoinGecko gratuito: **4-6 llamadas por minuto**, sin headers de cuota. El límite
lo aplica Cloudflare en el borde —hasta las respuestas cacheadas consumen cupo—
y `per_page` máximo real es 250: pedir más devuelve 100 **en silencio**.

Con 3.000 coins son 12 llamadas y los 429 son inevitables: la estrategia es
recuperarse bien, no evitarlos. Refresco completo en ~2m10s.

## Reglas que no se negocian

- **Si escribís `httpx.get()` fuera de `backend/fuentes/`, algo está mal.**
- Toda respuesta declara su vigencia: `calculado_at`, `fuente_hasta`.
- Todo canal de stream declara su `retencion`.
- La respuesta cruda de la fuente se guarda siempre.
