# Sistema de Reservas de Equipamiento de Laboratorio

Solución local, determinista y verificable para gestionar disponibilidad, reservas y cancelaciones con preservación histórica sobre un inventario fijo de unidades físicas de laboratorio. Desarrollada aplicando Ingeniería de Software asistida por un agente de programación bajo supervisión humana explícita.

> **Ejecución 100 % local y sin cuentas externas:** Ni la aplicación ni su suite de pruebas realizan llamadas a modelos de IA ni dependen de servicios pagos o credenciales del autor.

---

## 1. Especificación breve

### Problema y alcance
La coordinación del laboratorio necesita reemplazar una planilla manual propensa a dos errores: confirmar la misma unidad física en horarios superpuestos y mantener bloqueados horarios cuya reserva fue cancelada (o perder el historial al borrar filas).

- **Dentro del alcance:** Lectura del inventario precargado fijo (`MIC-01`, `MIC-02`, `OSC-01`, `MUL-01`, `FUE-01`), consulta de disponibilidad por unidad e intervalo, creación de reservas individuales identificables, cancelación lógica conservando ID y datos originales liberando el horario, consulta del historial y persistencia local recuperable tras reiniciar la aplicación.
- **Fuera de alcance:** Alta/baja/edición de inventario, autenticación y roles reales, notificaciones, pagos, integraciones externas, interfaz gráfica compleja, despliegue en nube y concurrencia distribuida multiproceso.

### Requisitos, reglas de negocio y supuestos clave
- **Requisitos funcionales (`RF-01`..`RF-05`):** Listado de unidades (`RF-01`), disponibilidad (`RF-02`), alta de reserva con ID `RES-XXXX` (`RF-03`), cancelación conservando historial (`RF-04`) y persistencia/consulta histórica (`RF-05`).
- **Reglas e invariantes (`RN-01`..`RN-07`):**
  - Unidad exacta existente en inventario (`RN-01`); solicitante ficticio no vacío ni de solo espacios tras `strip()` (`RN-02`); fechas/horas válidas con `start < end` (`RN-03`).
  - **Intervalos semiabiertos `[start, end)` (`RN-04`):** Dos rangos se superponen si y solo si `A.start < B.end` y `B.start < A.end`. Se rechazan superposiciones activas en la misma unidad (`10:00–11:00` rechaza `10:30–11:30`), se **permiten turnos consecutivos** (`10:00–11:00` permite `11:00–12:00`) y se **permiten reservas simultáneas en unidades distintas** (`MIC-01` y `MIC-02`).
  - Una reserva `CANCELLED` conserva sus datos pero no bloquea disponibilidad (`RN-05`); no puede cancelarse dos veces (`RN-06`).
  - **Simetría (`RN-07`):** La consulta de disponibilidad ejecuta exactamente la misma validación y cálculo de conflicto que la creación.
- **Supuestos explícitos (`SUP-01`..`SUP-05`):**
  - **Zona horaria y formato (`SUP-01`):** Hora local uniforme del laboratorio (`America/Argentina/Buenos_Aires`, `UTC-3`), formato ISO-8601 local con fecha y hora obligatorias (`YYYY-MM-DDTHH:MM` o `YYYY-MM-DDTHH:MM:SS`, *timezone-naive*). Se rechazan cadenas de solo fecha o con offsets horarios heterogéneos (`Z`, `-03:00`).
  - **Fechas pasadas y límites (`SUP-02`, `SUP-03`):** Se permite cualquier fecha calendáricamente válida con `start < end` sin restringir contra el reloj actual del sistema ni imponer topes arbitrarios de duración/anticipación, garantizando que las pruebas y ejemplos sean deterministas y reproducibles en cualquier fecha de evaluación.
  - **Persistencia y concurrencia local (`SUP-04`, `SUP-05`):** Archivos JSON separados y cerrojo reentrante `threading.RLock` + reemplazo atómico `os.replace`.

### Criterios de aceptación y trazabilidad
La especificación completa y detallada se encuentra en [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md). Su versión inicial (`v1.0` en commit `7e80e4e`) y su evolución a `v1.1` (commit `32ac9f6`, refinando `SUP-05` a `threading.RLock` y consolidando el contrato de errores HTTP) son recuperables en Git mediante:

```powershell
git log -p docs/SPECIFICATION.md
```

| Criterio / Regla | Qué verifica | Implementación principal | Pruebas automáticas |
| :--- | :--- | :--- | :--- |
| `RF-01` | Inventario fijo de 5 unidades | [`json_repositories.py`](src/lab_reservations/infrastructure/json_repositories.py) | `test_list_preloaded_inventory_units`, `test_http_get_units_returns_preloaded_inventory` |
| `CA-01` (`RF-02`, `RF-03`) | Creación válida y bloqueo de disponibilidad | [`services.py`](src/lab_reservations/application/services.py) | `test_valid_creation_and_availability_block`, `test_http_valid_creation_and_availability_check` |
| `CA-02` (`RN-04`) | Rechazo de superposición en misma unidad activa | [`value_objects.py`](src/lab_reservations/domain/value_objects.py) | `test_overlap_rejected_on_same_active_unit`, `test_http_rejects_overlap_...` |
| `CA-03` (`RN-04`) | Límites consecutivos permitidos (`end == start`) | [`value_objects.py`](src/lab_reservations/domain/value_objects.py) | `test_consecutive_boundaries_allowed_on_same_unit`, `test_http_rejects_overlap_...` |
| `CA-04` (`RN-04`) | Unidades distintas simultáneas permitidas | [`services.py`](src/lab_reservations/application/services.py) | `test_simultaneous_reservations_allowed_on_distinct_units`, `test_http_rejects_overlap_...` |
| `CA-05` (`RN-01`..`RN-03`, `RN-07`) | Rechazo simétrico de unidad/solicitante/fechas inválidas | [`value_objects.py`](src/lab_reservations/domain/value_objects.py), [`services.py`](src/lab_reservations/application/services.py) | `test_unknown_unit_...`, `test_empty_or_whitespace_...`, `test_invalid_dates_...`, `test_http_invalid_inputs_...` |
| `CA-06` (`RF-04`, `RN-05`, `RN-06`) | Cancelación conserva ID/datos y libera horario | [`entities.py`](src/lab_reservations/domain/entities.py), [`services.py`](src/lab_reservations/application/services.py) | `test_cancellation_preserves_history_and_frees_slot`, `test_http_cancellation_...` |
| `CA-07` (`RF-05`, `SUP-04`) | Persistencia de activas y canceladas tras reiniciar | [`json_repositories.py`](src/lab_reservations/infrastructure/json_repositories.py), [`app.py`](src/lab_reservations/api/app.py) | `test_survival_of_active_and_cancelled_reservations_across_restart`, `test_http_app_restart_...` |

---

## 2. Solución

### Estructura y decisiones técnicas
Arquitectura en **Capas Limpias Ligeras** (`api` / `infrastructure` → `application` → `domain`):

```text
.
├── AGENTS.md                                      # Reglas operativas del agente y Adaptación A
├── .agents/skills/persistence-verification/       # Skill del agente (Adaptación B de persistencia)
├── data/
│   ├── inventory.json                             # Catálogo precargado fijo (versionado, solo lectura)
│   └── reservations.json                          # Estado persistente en ejecución (ignorado en Git)
├── docs/
│   ├── SPECIFICATION.md                           # Especificación completa y su evolución (v1.0 -> v1.1)
│   └── PROGRESS_AND_DECISIONS.md                  # Progreso, ADRs, 3 episodios y verificaciones
├── src/lab_reservations/
│   ├── domain/                                    # Entidades, TimeInterval y excepciones (0 deps externas)
│   ├── application/                               # Puertos y casos de uso (ReservationService)
│   ├── infrastructure/                            # Repositorios JSON con RLock y escritura atómica
│   ├── api/                                       # Aplicación HTTP REST FastAPI y esquemas Pydantic
│   └── scripts/manage_data.py                     # CLI explícita de carga inicial (`init`) y `reset`
├── tests/
│   ├── unit/test_domain_and_service.py            # 28 pruebas unitarias puras
│   ├── integration/test_json_persistence.py       # 5 pruebas de persistencia JSON, concurrencia y CLI
│   └── api/test_http_api.py                       # 6 pruebas HTTP E2E incluyendo reinicio de app
├── pyproject.toml                                 # Metadatos y declaración de dependencias
└── requirements.lock.txt                          # Versiones exactas bloqueadas para reproducción fiel
```

### Requisitos previos y versiones verificadas
- **Sistema y runtime:** Python `>= 3.11` (verificado con `Python 3.12.0` y `pip 23.2.1` en Windows; compatible con Linux/macOS ajustando la activación de `.venv`).
- **Dependencias principales fijadas en [`requirements.lock.txt`](requirements.lock.txt):** `fastapi==0.162.0`, `uvicorn==0.54.0`, `pydantic==2.14.2`, `pytest==8.4.2`, `httpx==0.28.1`.

### Instalación reproducible

En **Windows (PowerShell)**:
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```
*(En Linux/macOS reemplazar `.\.venv\Scripts\python.exe` por `./.venv/bin/python`).*

### Persistencia, carga inicial y reinicio de datos
- **Dónde persisten los datos:**
  - `data/inventory.json`: catálogo precargado de las 5 unidades físicas (versionado en Git, **solo lectura**; la aplicación nunca lo modifica).
  - `data/reservations.json`: almacén operativo JSON con contador secuencial e historial completo de reservas `ACTIVE` y `CANCELLED` (se crea automáticamente vacío si no existe al iniciar y se actualiza mediante escritura atómica `.tmp` + `os.fsync` + `os.replace`).
- **Carga inicial segura (no borra reservas existentes):**
  ```powershell
  .\.venv\Scripts\python.exe -m lab_reservations.scripts.manage_data init
  ```
- **Reinicio limpio de datos (`reset`):**
  > **ADVERTENCIA IMPORTANTE:** Ejecutar `manage_data reset --confirm` **BORRA permanentemente todas las reservas activas y canceladas** almacenadas en `data/reservations.json` (restableciendo la secuencia a `RES-0001`), aunque conserva intacto `data/inventory.json`. En cambio, **detener y volver a iniciar el servidor de la aplicación NO borra datos** y recupera todo el historial.
  ```powershell
  .\.venv\Scripts\python.exe -m lab_reservations.scripts.manage_data reset --confirm
  ```

### Ejecución de pruebas y de la aplicación
- **Ejecutar todas las pruebas automáticas (39 tests, incluye reinicio automático en disco):**
  ```powershell
  .\.venv\Scripts\python.exe -m pytest
  ```
- **Iniciar el servidor HTTP REST local:**
  ```powershell
  .\.venv\Scripts\python.exe -m uvicorn lab_reservations.api.app:app --host 127.0.0.1 --port 8000
  ```
  Documentación OpenAPI interactiva disponible localmente en `http://127.0.0.1:8000/docs`.

### Ejemplo reproducible de entrada y salida (y prueba manual de reinicio)

Con el servidor corriendo en `http://127.0.0.1:8000`:

1. **Consultar inventario (`GET /units`) → `200 OK`:**
   ```bash
   curl.exe -s http://127.0.0.1:8000/units
   ```
   ```json
   [
     {"id": "MIC-01", "name": "Microscopio digital"},
     {"id": "MIC-02", "name": "Microscopio digital"},
     {"id": "OSC-01", "name": "Osciloscopio"},
     {"id": "MUL-01", "name": "Multímetro"},
     {"id": "FUE-01", "name": "Fuente de alimentación"}
   ]
   ```

2. **Crear reserva válida (`POST /reservations`) → `201 Created`:**
   ```bash
   curl.exe -s -X POST http://127.0.0.1:8000/reservations -H "Content-Type: application/json" -d "{\"unit_id\":\"MIC-01\",\"requester\":\"Dra. Valeria Méndez (Ficticio)\",\"start\":\"2026-11-10T10:00\",\"end\":\"2026-11-10T11:00\"}"
   ```
   ```json
   {
     "id": "RES-0001",
     "unit_id": "MIC-01",
     "requester": "Dra. Valeria Méndez (Ficticio)",
     "start": "2026-11-10T10:00",
     "end": "2026-11-10T11:00",
     "status": "ACTIVE",
     "created_at": "2026-11-01T05:15",
     "cancelled_at": null
   }
   ```

3. **Intentar horario superpuesto `10:30–11:30` en `MIC-01` → `409 Conflict`:**
   ```bash
   curl.exe -s -X POST http://127.0.0.1:8000/reservations -H "Content-Type: application/json" -d "{\"unit_id\":\"MIC-01\",\"requester\":\"Ing. Martín Rojas (Ficticio)\",\"start\":\"2026-11-10T10:30\",\"end\":\"2026-11-10T11:30\"}"
   ```
   ```json
   {
     "error": {
       "code": "RESERVATION_OVERLAP",
       "message": "La unidad 'MIC-01' ya posee reservas activas superpuestas (RES-0001).",
       "details": {"unit_id": "MIC-01", "conflicting_reservation_ids": ["RES-0001"]}
     }
   }
   ```

4. **Consultar turno consecutivo `11:00–12:00` (`GET /availability`) → `200 OK` (`available: true`):**
   ```bash
   curl.exe -s "http://127.0.0.1:8000/availability?unit_id=MIC-01&start=2026-11-10T11:00&end=2026-11-10T12:00"
   ```
   ```json
   {
     "unit_id": "MIC-01",
     "start": "2026-11-10T11:00",
     "end": "2026-11-10T12:00",
     "available": true,
     "conflicting_reservation_ids": []
   }
   ```

5. **Cancelar reserva conservando historial y liberando horario (`POST /reservations/RES-0001/cancel`) → `200 OK`:**
   ```bash
   curl.exe -s -X POST http://127.0.0.1:8000/reservations/RES-0001/cancel
   ```
   ```json
   {
     "id": "RES-0001",
     "unit_id": "MIC-01",
     "requester": "Dra. Valeria Méndez (Ficticio)",
     "start": "2026-11-10T10:00",
     "end": "2026-11-10T11:00",
     "status": "CANCELLED",
     "created_at": "2026-11-01T05:15",
     "cancelled_at": "2026-11-01T05:16"
   }
   ```
   *(Para verificar persistencia manualmente: crear una segunda reserva activa `RES-0002`, detener `uvicorn` con `Ctrl+C`, volver a iniciar el mismo comando `uvicorn` sin ejecutar `reset` y consultar `curl.exe -s http://127.0.0.1:8000/reservations`: se observarán `RES-0001` en `CANCELLED` con horario libre y `RES-0002` en `ACTIVE` con horario bloqueado).*

### Pendientes y limitaciones declaradas
- **Concurrencia de proceso único:** El bloqueo con `threading.RLock` + `os.replace` garantiza consistencia dentro de una instancia local de servidor; no está diseñado para múltiples procesos/workers escribiendo simultáneamente el mismo archivo JSON.
- **Escala local:** Cada escritura serializa la colección completa en JSON, óptimo para la escala operativa de un laboratorio pequeño. Para miles de reservas históricas bastaría implementar un adaptador SQLite/PostgreSQL para `ReservationRepository` sin alterar `domain/` ni `application/`.
- **Advertencia menor de terceros en tests:** En `fastapi 0.162.0` + `starlette 1.10.0`, `TestClient` emite un `StarletteDeprecationWarning` interno sugiriendo `httpx2` a futuro; no afecta la ejecución de la API ni de las pruebas.

---

## 3. Preparación del agente

- **Entorno (*Harness*) y modelo:** Se utilizó un único agente de programación en **Google Antigravity IDE** sobre Windows, coordinando lectura/escritura de archivos del repositorio y ejecución de comandos en PowerShell. El modelo seleccionado en la interfaz fue *Gemini 4 Argon (High)* (se declara explícitamente que el identificador interno exacto de checkpoint/build del modelo y la versión interna de build del IDE no están expuestos en el contexto visible, sin inventarlos). Se eligió por su capacidad para respetar invariantes formales de arquitectura y soportar reglas y *skills* nativas en el repositorio.
- **Instrucciones y contexto realmente usados:**
  - [`AGENTS.md`](AGENTS.md): Archivo de reglas en la raíz del repositorio (descubierto y cargado automáticamente por Antigravity sin configuración oculta externa). Establece `docs/SPECIFICATION.md` como fuente de verdad, prohíbe datos personales reales/credenciales, fija las capas limpias y prohíbe commits sin aprobación humana.
  - **Contexto suministrado y excluido:** En cada episodio se acotó el contexto a las capas pertinentes (ej. en el Episodio 1 se excluyeron persistencia e interfaz HTTP para evitar filtración de infraestructura hacia el dominio). Se excluyeron por completo datos reales de personas y transcripciones crudas de conversación.
- **Herramientas, permisos y controles humanos aplicados:** El agente tuvo permiso para crear/editar archivos dentro de `c:\tareaIngenieria` y ejecutar comandos locales de verificación (`git`, `python`, `pip`, `pytest`), pero con **4 puntos reales de aprobación humana obligatoria** antes de cada commit: (1) revisión de `SPECIFICATION.md` v1.0 y `AGENTS.md`, (2) revisión del Episodio 1, (3) revisión del Episodio 2 y (4) revisión del Episodio 3 más ejecución directa de comandos por la persona responsable.
- **Adaptaciones específicas comprobables y evidencia de uso real:**
  1. **Adaptación A — Semántica `[start, end)` y simetría de disponibilidad ([`AGENTS.md`](AGENTS.md)):** Exige encapsular intervalos en `TimeInterval` usando únicamente `self.start < other.end and other.start < self.end` y compartir la ruta de validación entre disponibilidad y creación. *Evidencia:* [`value_objects.py`](src/lab_reservations/domain/value_objects.py), [`services.py`](src/lab_reservations/application/services.py) y tests `CA-02`/`CA-03`/`CA-05`.
  2. **Adaptación B — Skill de persistencia JSON atómica y prueba de reinicio ([`.agents/skills/persistence-verification/SKILL.md`](.agents/skills/persistence-verification/SKILL.md)):** Runbook activado explícitamente en el Episodio 2 para separar `inventory.json` de `reservations.json`, escribir con `.tmp` + `os.fsync` + `os.replace`, exigir `--confirm` con advertencia en `reset` y probar la recuperación de activas y canceladas tras reiniciar. *Evidencia:* [`json_repositories.py`](src/lab_reservations/infrastructure/json_repositories.py), [`manage_data.py`](src/lab_reservations/scripts/manage_data.py) y [`test_json_persistence.py`](tests/integration/test_json_persistence.py).
- **Retención del progreso:** Estado por fases, ADRs, episodios y verificaciones versionados continuamente en [`docs/PROGRESS_AND_DECISIONS.md`](docs/PROGRESS_AND_DECISIONS.md).

---

## 4. Registro de decisiones y delegación

El detalle completo de alternativas, consecuencias y tablas de verificación se conserva en [`docs/PROGRESS_AND_DECISIONS.md`](docs/PROGRESS_AND_DECISIONS.md). Resumen ejecutivo:

### Decisiones significativas (`ADR-01`..`ADR-05`)
1. **`ADR-01` (Python 3.12 + FastAPI + pytest):** Elegido frente a Node/TS o Java por disponibilidad local inmediata (`Python 3.12.0`), expresividad de `dataclasses` inmutables y reproducción rápida con `requirements.lock.txt`.
2. **`ADR-02` (API HTTP REST local + `manage_data`):** Elegida frente a una CLI pura para reflejar contratos HTTP semánticos (`201`, `404`, `409`, `422`), reservando un script explícito para `init`/`reset`.
3. **`ADR-03` (Archivos JSON separados con escritura atómica y `RLock`):** Elegido frente a SQLite o un único JSON combinado para permitir inspección directa del historial en texto plano y resetear reservas sin riesgo sobre `data/inventory.json`.
4. **`ADR-04` (Capas Limpias Ligeras):** Aísla `domain/` y `application/` de FastAPI y del sistema de archivos, asegurando la simetría `RN-07` por construcción.
5. **`ADR-05` (ISO local sin bloqueo de fechas pasadas):** Elimina errores de comparación *naive* vs *aware* en un único laboratorio físico y evita que los tests o ejemplos documentados caduquen en futuras fechas de corrección.

### Tres episodios reales de delegación

1. **Episodio 1 — Dominio puro, casos de uso y pruebas unitarias (`RF-01`..`RF-04`, `RN-01`..`RN-07`, `CA-01`..`CA-06`):**
   - *Contexto e instrucción:* `docs/SPECIFICATION.md` (`7e80e4e`), `AGENTS.md` (`6409d57`) e `inventory.json`, excluyendo persistencia e interfaz HTTP. Instrucción aprobada: *"he leído ambos documentos y todo me parece bien. podemos proceder"*.
   - *Acción del agente:* Creó `pyproject.toml`, `.venv`, `requirements.lock.txt` (reescrito en UTF-8 sin BOM), `domain/`, `application/` y 28 pruebas unitarias (`28 passed`).
   - *Decisión humana:* **Aceptado** tras revisar `value_objects.py` y `services.py`, comprobando la fórmula semiabierta `[start, end)` y la validación compartida `_validate_unit_and_interval`.
   - *Evidencia:* Commit `54ddda6`, [`src/lab_reservations/domain/`](src/lab_reservations/domain/), [`src/lab_reservations/application/`](src/lab_reservations/application/), [`tests/unit/test_domain_and_service.py`](tests/unit/test_domain_and_service.py).

2. **Episodio 2 — Persistencia JSON atómica, `manage_data` y supervivencia al reinicio (`RF-01`, `RF-05`, `SUP-04`, `SUP-05`, `CA-07`):**
   - *Contexto e instrucción:* Activación y lectura real de `.agents/skills/persistence-verification/SKILL.md` + contratos de `ports.py`. Instrucción tras revisar Episodio 1: *"me parece que está todo en orden. sigamos adelante."*
   - *Acción del agente:* Implementó `JsonInventoryRepository`, `JsonReservationRepository` (con `threading.RLock` reentrante y `.tmp` + `os.fsync` + `os.replace`), `manage_data.py` (refinando `reset --confirm` para reemplazar atómicamente sin `unlink()` previo) y 5 pruebas integrales en disco (`33 passed` acumuladas).
   - *Decisión humana:* **Aceptado** tras revisar la atomicidad en `json_repositories.py`, las salvaguardas de `manage_data.py` y las pruebas de recuperación tras reinicio.
   - *Evidencia:* Commit `7371a93`, [`json_repositories.py`](src/lab_reservations/infrastructure/json_repositories.py), [`manage_data.py`](src/lab_reservations/scripts/manage_data.py), [`test_json_persistence.py`](tests/integration/test_json_persistence.py).

3. **Episodio 3 — API HTTP REST (`FastAPI`), especificación `v1.1` y pruebas E2E (`RF-01`..`RF-05`, `CA-01`..`CA-07`):**
   - *Contexto e instrucción:* `SPECIFICATION.md`, `AGENTS.md`, `services.py` y `json_repositories.py`. Instrucción tras revisar Episodio 2: *"esta todo en orden, sigamos adelante."*
   - *Acción del agente:* Actualizó `SPECIFICATION.md` a `v1.1`, implementó `api/schemas.py` y `api/app.py` (corrigiendo `HTTP_422_UNPROCESSABLE_ENTITY` -> `HTTP_422_UNPROCESSABLE_CONTENT` al observar la advertencia real de Starlette `1.10.0` en `pytest`) y sumó 6 pruebas HTTP E2E incluyendo reinicio completo de la app (`39 passed`).
   - *Decisión humana:* **Aceptado** tras revisar `SPECIFICATION.md` `v1.1`, `api/app.py` y comprobar personalmente en terminal las 39 pruebas y los subcomandos `init` / `reset --confirm`.
   - *Evidencia:* Commit `32ac9f6`, [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md), [`app.py`](src/lab_reservations/api/app.py), [`schemas.py`](src/lab_reservations/api/schemas.py), [`test_http_api.py`](tests/api/test_http_api.py).

### Síntesis de verificaciones (Agente vs. Comprobación Humana)
- **Ejecutado por el agente:** Suite completa `.\.venv\Scripts\python.exe -m pytest` en `Python 3.12.0` / `pytest 8.4.2` → **`39 passed in 5.05s`** (28 unitarias + 5 persistencia/concurrencia/CLI + 6 HTTP E2E y reinicio).
- **Ejecutado directamente por la persona responsable:** Verificación de `Python 3.12.0`, corrida completa `.\.venv\Scripts\python.exe -m pytest` (`39 passed`), `manage_data init` y `manage_data reset --confirm`, confirmando ausencia de fallos y que `data/inventory.json` permanece intacto. Ver tabla detallada en [`docs/PROGRESS_AND_DECISIONS.md` (Sección 4)](docs/PROGRESS_AND_DECISIONS.md).
