# LocalDoc IA

LocalDoc IA es un sistema local para procesar, almacenar y consultar comprobantes fiscales, facturas, tickets y recibos. Combina modelos de lenguaje y visión ejecutados con **Ollama**, un servidor **MCP** (Model Context Protocol), **PostgreSQL** y un bot de **Telegram**.

El objetivo es poder enviar una factura desde Telegram, extraer sus datos con un modelo local, guardarla en la base y luego consultarla en lenguaje natural: factura de mayor importe, gastos por proveedor, comparación de períodos, búsqueda de productos, exportación de reportes, etc.

---

## Características

### Procesamiento documental

- **PDFs digitales:** extracción de texto nativo con PyMuPDF.
- **PDFs escaneados e imágenes:** renderizado y análisis visual con un modelo VLM de Ollama.
- Si un PDF tiene alguna página sin texto seleccionable, se renderiza el documento completo y se envía al modelo visual para conservar el contexto entre páginas.
- **Formatos admitidos:** PDF, JPG, JPEG, PNG, TIF, TIFF, BMP y WEBP.
- **Detección de duplicados:** se calcula el SHA-256 del archivo antes de procesarlo.
- **Trazabilidad:** cada documento se registra como `pending` mientras se procesa, pasa a `completed` al guardarse y queda en `failed` si ocurre un error.
- **Validación con Pydantic:** normaliza fechas, CUIT de 11 dígitos y códigos de moneda antes de guardar.
- **Advertencias de calidad:** informa cuando no pudo identificar proveedor, fecha, total o ítems.

### Datos almacenados

- Datos del comprobante: tipo, punto de venta, número, fechas, moneda, subtotal, impuestos, descuentos y total.
- Datos del proveedor y del cliente.
- Ítems o conceptos de la factura con cantidad, precio unitario, alícuota e importe.
- Observaciones y notas recuperadas del documento.
- Texto extraído y JSON original validado (`extracted_data`).

### Consulta conversacional

- Bot de Telegram con memoria de conversación.
- El agente decide qué herramienta MCP usar y devuelve una respuesta en español.
- Consultas disponibles:
  - Factura con mayor o menor saldo.
  - Promedio de gasto por factura.
  - Ranking de facturas más caras.
  - Búsquedas por proveedor, CUIT, número, fecha, moneda o rango de importes.
  - Comparación entre dos períodos.
  - Consulta de productos o servicios facturados.
  - Generación de reportes CSV.

### Reportes

- Exportación CSV en UTF-8 con BOM y separador `;`.
- Incluye columnas para observaciones e ítems detallados.
- Los archivos se guardan en `reports/telegram/` y el bot los adjunta en la conversación.

---

## Arquitectura

```text
Telegram
   │
   ▼
Bot de Telegram ──► Servicio de procesamiento ──► PostgreSQL
   │                       │
   │                       ├── PDF con texto ──► Ollama (texto)
   │                       └── Imagen / PDF escaneado ──► Ollama (visión)
   │
   ▼
Agent Harness ──► Ollama (modelo con herramientas)
   │
   ▼
Servidor MCP ──► Consultas SQL ──► PostgreSQL
   │
   └──► Generación de reportes CSV
```

El agente trabaja con un ciclo de razonamiento:

1. Recibe el mensaje del usuario y el historial reciente.
2. Consulta a Ollama con las herramientas MCP disponibles.
3. Ejecuta las herramientas que el modelo solicite.
4. Devuelve los resultados al modelo.
5. Repite hasta obtener una respuesta final o alcanzar `MAX_AGENT_STEPS`.

---

## Herramientas MCP

El servidor MCP expone seis herramientas:

| Herramienta | Para qué sirve |
|---|---|
| `obtener_estadisticas` | Factura con mayor/menor saldo, comparativa de extremos, total acumulado, ticket promedio, top 3 y proveedor principal. |
| `buscar_documentos` | Búsqueda por texto, proveedor, CUIT, cliente, ítems, observaciones, fechas, moneda y rango de importes. Permite ordenar por `total`, `fecha`, `proveedor` o `id`. |
| `comparar_periodos` | Compara cantidad de facturas y gasto entre dos períodos, con diferencia absoluta, variación porcentual y tendencia. |
| `buscar_items_productos` | Busca productos o servicios en las líneas de detalle y devuelve precios unitarios, cantidades y proveedores. |
| `consultar_gastos` | Totales, subtotales e impuestos agrupados por moneda y proveedor. |
| `generar_reporte` | Genera un CSV con los filtros y el ordenamiento indicados. |

Los importes de monedas diferentes no se suman entre sí. Las estadísticas y los gastos se agrupan por moneda.

El servidor también puede ejecutarse de forma independiente mediante transporte STDIO:

```bash
uv run python -m localdoc_ia.mcp.server
```

---

## Estructura del Proyecto

```text
localdoc-ia/
├── data/
│   ├── inbox/telegram/     # Archivos originales recibidos por Telegram
│   └── samples/            # Documentos de ejemplo para pruebas manuales
├── reports/
│   ├── telegram/           # Reportes CSV generados para enviar por Telegram
│   └── *.json              # Salidas JSON de probar_extraccion.py
├── src/
│   └── localdoc_ia/
│       ├── agent/          # Agent harness, prompts y llamadas a Ollama
│       ├── database/       # Modelos SQLAlchemy, conexión, consultas y migraciones
│       ├── ingestion/      # Extracción de texto nativo y renderizado para visión
│       ├── mcp/            # Servidor MCP y herramientas expuestas
│       ├── reporting/      # Generación de reportes CSV
│       ├── schemas/        # Modelos Pydantic para comprobantes
│       ├── services/       # Orquestador del flujo documental
│       ├── telegram/       # Bot de Telegram
│       ├── config.py       # Configuración y variables de entorno
│       └── main.py         # Punto de entrada del bot
├── tests/                  # Pruebas con pytest
├── probar_extraccion.py    # Prueba manual de extracción de un archivo
├── pyproject.toml          # Dependencias y configuración del proyecto
└── .env.example            # Ejemplo de variables de entorno
```

---

## Requisitos

- Python 3.12 o superior.
- [uv](https://docs.astral.sh/uv/) para instalar dependencias y ejecutar el proyecto.
- PostgreSQL 14 o superior.
- Ollama instalado y ejecutándose.
- Modelos de Ollama:
  - `qwen2.5:7b` para texto y uso de herramientas.
  - `qwen2.5vl:7b` para visión.

Podés usar otros modelos configurando `OLLAMA_MODEL` y `OLLAMA_VISION_MODEL`, pero deben ser compatibles con herramientas y con salida JSON respectivamente.

---

## Puesta en Marcha

### 1. Instalar dependencias

```bash
uv sync
```

### 2. Preparar Ollama

```bash
ollama serve
ollama pull qwen2.5:7b
ollama pull qwen2.5vl:7b
```

### 3. Crear la base de datos

Crear un usuario y una base en PostgreSQL. Por ejemplo:

```sql
CREATE USER localdoc_user WITH PASSWORD 'cambiar_password';
CREATE DATABASE localdoc OWNER localdoc_user;
```

### 4. Configurar `.env`

Copiar el ejemplo y completar los valores:

```bash
cp .env.example .env
```

Variables principales:

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `APP_NAME` | `LocalDoc AI` | Nombre visible en el bot, el CLI y el servidor MCP. |
| `APP_ENV` | `development` | Entorno de ejecución; se muestra en los logs de inicio. |
| `LOG_LEVEL` | `INFO` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `DATABASE_URL` | — | Cadena de conexión de SQLAlchemy. Ejemplo: `postgresql+psycopg://usuario:password@127.0.0.1:5432/localdoc`. |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | URL del servidor Ollama. También se acepta `OLLAMA_BASE_URL`. |
| `OLLAMA_MODEL` | `qwen2.5:7b` | Modelo de texto y herramientas. |
| `OLLAMA_VISION_MODEL` | `qwen2.5vl:7b` | Modelo de visión. |
| `OLLAMA_TEMPERATURE` | `0.0` | Temperatura de generación del agente. |
| `OLLAMA_TIMEOUT` | `120` | Timeout de las llamadas a Ollama, en segundos. |
| `OLLAMA_NUM_CTX` | `16384` | Ventana de contexto del agente. No bajar de 8192 si se usan herramientas. |
| `OLLAMA_NUM_PREDICT` | `1024` | Máximo de tokens de salida por respuesta. |
| `MAX_TOOL_RESULT_CHARS` | `30000` | Máximo de caracteres que se envían al modelo por resultado MCP. |
| `MAX_AGENT_STEPS` | `5` | Cantidad máxima de rondas de herramientas por consulta. |
| `MAX_CONVERSATION_TURNS` | `6` | Intercambios que se conservan en memoria. |
| `DOCUMENTS_DIR` | `./data` | Directorio base para documentos. |
| `INBOX_DIR` | `./data/inbox` | Directorio donde se guardan los archivos recibidos. |
| `SAMPLES_DIR` | `./data/samples` | Directorio de documentos de ejemplo. |
| `REPORTS_DIR` | `./reports` | Directorio base de los reportes generados. |
| `MAX_FILE_SIZE_MB` | `20` | Tamaño máximo de archivo. Telegram limita la descarga a 20 MB. |
| `OCR_LANG` | `spa` | Idioma usado por el módulo OCR opcional. |
| `OCR_DPI` | `300` | DPI usado al renderizar páginas de PDF para el modelo visual. |
| `TELEGRAM_BOT_TOKEN` | — | Token del bot de Telegram. |
| `TELEGRAM_ALLOWED_USER_IDS` | — | IDs de Telegram autorizados, separados por comas. |

> El bot solo responde en chats privados y a los IDs incluidos en `TELEGRAM_ALLOWED_USER_IDS`. Las rutas relativas se resuelven desde la raíz del proyecto.

### 5. Inicializar la base de datos

```bash
uv run python -m localdoc_ia.database.init_db
```

Este comando crea las tablas faltantes y aplica las migraciones idempotentes del proyecto.

### 6. Ejecutar el bot

```bash
uv run python -m localdoc_ia.telegram.bot
```

También se puede usar el comando registrado:

```bash
uv run localdoc-ia
```

### 7. Probar la extracción de un archivo

```bash
uv run python probar_extraccion.py data/samples/imagen.png
```

El script sirve para imágenes JPG, PNG, BMP o WEBP y para PDFs digitales: muestra los datos extraídos y guarda una copia JSON del resultado en `reports/`. Para PDFs escaneados, usá el bot de Telegram, que renderiza el documento completo y lo procesa con el modelo de visión.

---

## Uso del Bot

Comandos disponibles:

| Comando | Descripción |
|---|---|
| `/start` | Inicia la conversación y muestra las funcionalidades. |
| `/ayuda` | Muestra la ayuda. |
| `/reset` | Borra la memoria de la conversación actual. |

Ejemplos de consultas:

```text
¿Cuál es la factura con mayor saldo hasta ahora?
¿Cuál es el promedio de gasto por factura?
Buscá las facturas del proveedor Previnca
¿Cuánto gastamos en carnicería?
Compará enero de 2026 con febrero de 2026
Generá un reporte de las facturas de este año
```

---

## Pruebas

```bash
uv run pytest
```

La suite incluye pruebas unitarias y de integración. Las pruebas de integración usan la base configurada en `DATABASE_URL` y esperan los documentos de ejemplo del proyecto; si la base está vacía o no tiene esos registros, esas pruebas pueden fallar.

---

## Solución de Problemas

### El bot recibe el mensaje pero no responde o responde incompleto

Verificá que `OLLAMA_NUM_CTX` sea al menos `8192`. El valor recomendado es `16384`, porque el prompt del agente, las herramientas MCP y sus resultados superan el contexto por defecto de Ollama (4096 tokens).

Si el problema continúa:

```bash
ollama ps
```

Comprobá que el modelo esté cargado y que Ollama esté respondiendo. También podés reducir `MAX_TOOL_RESULT_CHARS` o aumentar `OLLAMA_TIMEOUT`.

### Ollama devuelve una respuesta vacía

- Confirmá que el modelo configurado esté instalado: `ollama list`.
- Verificá que el modelo sea compatible con herramientas y salida JSON.
- Revisá los logs del bot: los errores de Ollama se registran con detalle.

### El bot responde “No estás autorizado”

- El bot solo funciona en chats privados.
- El ID del usuario debe estar en `TELEGRAM_ALLOWED_USER_IDS`.
- Después de modificar `.env`, reiniciá el bot.

### Un documento figura como duplicado

El sistema identifica los archivos por su hash SHA-256. Si el mismo archivo ya fue procesado, informa el ID del documento existente. Para volver a procesarlo, primero debe eliminarse el registro correspondiente de la base.

### El reporte no llega por Telegram

- Verificá que el archivo exista en `reports/telegram/`.
- Comprobá que el bot tenga permisos de escritura sobre `reports/`.
- Revisá los logs para ver si el error ocurrió al generar el CSV o al enviarlo.

---

## Limitaciones

- La calidad de los datos extraídos depende del modelo local y de la calidad del documento.
- Los documentos con datos faltantes se guardan igualmente, pero generan advertencias para revisión.
- El flujo principal no usa Tesseract: los PDFs sin texto y las imágenes se procesan directamente con el modelo de visión.
- No se suman importes de monedas diferentes.
- El agente no ejecuta SQL arbitrario ni modifica facturas desde las herramientas MCP.
