# Progreso del Proyecto, Decisiones de Ingeniería y Delegación

Este documento versionado conserva el estado operativo del proyecto, el registro de decisiones arquitectónicas y técnicas (ADRs), la trazabilidad de los episodios reales de delegación al agente de programación y el registro de verificaciones ejecutadas.

---

## 1. Estado de Progreso

- [x] **Fase 1:** Inicialización del repositorio Git (`main`), `.gitignore` e inventario inicial (`data/inventory.json`).
- [x] **Fase 2:** Redacción y aprobación humana de la Especificación Inicial v1.0 (`docs/SPECIFICATION.md`).
- [x] **Fase 3:** Preparación y aprobación humana del agente (`AGENTS.md` + `.agents/skills/persistence-verification/SKILL.md`) y decisiones iniciales (`ADR-01`..`ADR-05`).
- [x] **Fase 4 — Episodio 1 de delegación:** Capa de dominio (`domain/`) y capa de aplicación (`application/`) con pruebas unitarias puras.
- [x] **Fase 4 — Episodio 2 de delegación:** Persistencia JSON atómica (`infrastructure/`), comando `manage_data` (`scripts/`) y pruebas de persistencia/reinicio.
- [x] **Fase 4 — Episodio 3 de delegación:** API HTTP REST local con FastAPI (`api/`) y suite integral de pruebas automáticas (`tests/`).
- [x] **Fase 5:** Ejecución y registro de verificaciones humanas reproducibles (automáticas + comandos `init`/`reset`).
- [x] **Fase 6:** Cierre documental del `README.md` y auditoría final del repositorio.

---

## 2. Registro de Decisiones Significativas (ADRs)

### `ADR-01` — Elección de lenguaje y ecosistema: Python 3.12
- **Decisión:** Implementar la solución en Python 3.12 utilizando `FastAPI` + `Uvicorn` para la capa HTTP y `pytest` + `httpx` para pruebas automatizadas, fijando versiones exactas en archivos de dependencias/bloqueo.
- **Alternativas evaluadas:** TypeScript/Node.js LTS; Java/C#; Python con librería estándar pura (`http.server` / CLI).
- **Motivo:** Python 3.12 está disponible localmente (`Python 3.12.0`), ofrece alta expresividad para modelar invariantes de dominio con `dataclasses` y `enum`, y permite ejecutar pruebas reproducibles en segundos sin pasos de compilación complejos ni cuentas externas.
- **Consecuencias:** Se requiere entorno virtual local (`.venv`) e instalación reproducible desde archivo de dependencias bloqueadas (`requirements.lock.txt` / `pyproject.toml`).

### `ADR-02` — Interfaz del sistema: API HTTP REST local
- **Decisión:** Exponer el sistema mediante una API HTTP REST local sobre `FastAPI` acompañada de un pequeño script auxiliar (`manage_data`) exclusivamente para inicialización/reinicio explícito del almacenamiento.
- **Alternativas evaluadas:** Aplicación exclusivamente de consola (CLI por subcomandos); interfaz gráfica web completa.
- **Motivo:** Una API REST local refleja una interfaz profesional estándar en ingeniería de software, permite mapear semánticamente errores de negocio a códigos HTTP (`201 Created`, `404 Not Found`, `409 Conflict`, `422 Unprocessable Entity`) y se testea determinísticamente con `httpx`/`TestClient` además de `curl` o PowerShell, sin caer en el costo fuera de alcance de un frontend gráfico.
- **Consecuencias:** La verificación manual requiere levantar el proceso `uvicorn` local, mientras que la suite automática verifica tanto endpoints HTTP como reinicio de instancias sin pasos manuales.

### `ADR-03` — Almacenamiento local: Archivos JSON separados con escritura atómica
- **Decisión:** Persistir el catálogo inmutable en `data/inventory.json` (solo lectura, versionado) y el historial de reservas en `data/reservations.json` (lectura/escritura con archivo temporal + `os.replace` y `threading.RLock`).
- **Alternativas evaluadas:** Base de datos relacional embebida (`SQLite`); un único archivo JSON combinando inventario y reservas.
- **Motivo:** El volumen de un laboratorio de 5 unidades es pequeño; JSON permite auditar a simple vista en cualquier editor el estado exacto persistido (`ACTIVE` vs `CANCELLED`), y separar ambos archivos permite reiniciar/limpiar las reservas sin riesgo de borrar el inventario precargado.
- **Consecuencias:** Toda escritura reescribe el archivo completo de reservas de forma atómica (óptimo para escala local pequeña; no diseñado para concurrencia distribuida multiproceso, la cual está fuera de alcance).

### `ADR-04` — Arquitectura interna: Capas Limpias / Hexagonal Ligera
- **Decisión:** Estructurar el paquete `lab_reservations` en `domain` (reglas puras e invariantes), `application` (servicio y puertos), `infrastructure` (repositorios JSON) y `api` (controladores HTTP).
- **Alternativas evaluadas:** Script monolítico o controladores FastAPI acoplados directamente a la lectura/escritura de JSON.
- **Motivo:** Desacoplar las reglas de negocio (`TimeInterval`, validaciones y estado de cancelación) del transporte HTTP y del formato JSON garantiza cohesión, facilita pruebas unitarias rápidas y asegura por construcción que `check_availability` y `create_reservation` compartan exactamente la misma lógica (`RN-07`).
- **Consecuencias:** Mayor cantidad de módulos pequeños y explícitos a cambio de trazabilidad directa entre requisitos y clases.

### `ADR-05` — Política temporal: Hora local uniforme sin bloqueo de fechas pasadas
- **Decisión:** Representar intervalos en formato ISO-8601 local con fecha y hora obligatorias (`YYYY-MM-DDTHH:MM[:SS]`, *timezone-naive* uniforme en hora del laboratorio `UTC-3`) y permitir cualquier fecha calendáricamente válida siempre que `start < end`.
- **Alternativas evaluadas:** Bloquear reservas anteriores a `datetime.now()`; exigir timestamps UTC con conversión de zonas horarias.
- **Motivo:** Al tratarse de un único laboratorio físico local, exigir un único formato local elimina errores por mezcla de fechas con y sin offset. No restringir contra el reloj de pared del sistema permite que los ejemplos del `README.md` y las pruebas automatizadas sean 100 % reproducibles en cualquier fecha futura en que se evalúe la entrega.
- **Consecuencias:** El sistema actúa como registro administrativo determinista de turnos y delega a la coordinación si desea cargar registros históricos o futuros.

---

## 3. Tres Episodios Reales de Delegación

*(Se completarán en tiempo real durante la Fase 4 con extractos reales, revisión humana y enlaces a commits/archivos verificables).*

### Episodio 1 — Dominio puro, casos de uso y pruebas unitarias (`RF-01`..`RF-04`, `RN-01`..`RN-07`, `CA-01`..`CA-06`)
- **Objetivo y requisito:** Configurar el empaquetado reproducible del proyecto (`pyproject.toml` + `requirements.lock.txt`) e implementar las capas `domain/` y `application/` sin dependencias de red ni de archivos, garantizando semántica de intervalos semiabiertos `[start, end)` (`RN-04`, Adaptación A), cancelación lógica inmutable (`RF-04`, `RN-05`, `RN-06`) y simetría total entre consulta de disponibilidad y creación (`RN-07`).
- **Contexto suministrado y extracto de instrucción:** Se suministraron `docs/SPECIFICATION.md` (commit `7e80e4e`), `AGENTS.md` (cargado automáticamente en el contexto del entorno Antigravity, commit `6409d57`) y `data/inventory.json`, excluyendo deliberadamente la persistencia en disco y la capa HTTP para aislar la lógica de negocio. Extracto de instrucción: *"he leído ambos documentos y todo me parece bien. podemos proceder"* sobre la propuesta acotada de ejecutar los commits base y el Episodio 1 (`domain/` + `application/` + pruebas unitarias).
- **Acción / resultado del agente:**
  - Configuró `pyproject.toml`, entorno virtual local `.venv` y archivo de bloqueo `requirements.lock.txt` (UTF-8 sin BOM).
  - Implementó `TimeInterval` (validación estricta de formato ISO local `YYYY-MM-DDTHH:MM[:SS]` sin zona horaria, `start < end` y `overlaps_with`), `EquipmentUnit`, `Reservation`, `ReservationStatus` y jerarquía de excepciones en `src/lab_reservations/domain/`.
  - Implementó protocolos `InventoryRepository` / `ReservationRepository` y `ReservationService` en `src/lab_reservations/application/` reutilizando `_validate_unit_and_interval` y `_find_active_conflicts` tanto en `check_availability` como en `create_reservation`.
  - Creó y ejecutó 28 pruebas unitarias parametrizadas en `tests/unit/test_domain_and_service.py` (`28 passed` en `pytest 8.4.2`).
- **Decisión humana (aceptar / corregir / rechazar) y motivo:** **Aceptado** tras revisar `value_objects.py`, `services.py` y el reporte de pruebas unitarias, verificando que la semántica semiabierta `[start, end)`, la normalización del solicitante y la ruta compartida de validación cumplen `RN-01`..`RN-07` sin acoplamiento externo.
- **Evidencia verificable (commit / archivos / pruebas):** Commit `54ddda6`; archivos [`src/lab_reservations/domain/`](../src/lab_reservations/domain/), [`src/lab_reservations/application/`](../src/lab_reservations/application/) y [`tests/unit/test_domain_and_service.py`](../tests/unit/test_domain_and_service.py).

### Episodio 2 — Persistencia JSON atómica, gestión de datos y prueba de supervivencia al reinicio (`RF-01`, `RF-05`, `SUP-04`, `SUP-05`, `CA-07`)
- **Objetivo y requisito:** Implementar los adaptadores `JsonInventoryRepository` y `JsonReservationRepository` en `infrastructure/`, el comando explícito `manage_data` (`init` y `reset --confirm`) en `scripts/` y la prueba automatizada de persistencia de reservas activas y canceladas tras detener y reiniciar la aplicación (`CA-07`).
- **Contexto suministrado y extracto de instrucción:** Se activó y leyó explícitamente la skill del proyecto `.agents/skills/persistence-verification/SKILL.md` (Adaptación B), junto con los contratos de `application/ports.py` y `data/inventory.json`, excluyendo aún la capa HTTP (`api/`). Extracto de instrucción tras aprobar el Episodio 1: *"me parece que está todo en orden. sigamos adelante."*
- **Acción / resultado del agente:**
  - Implementó `JsonInventoryRepository` (solo lectura estricta sobre `data/inventory.json`) y `JsonReservationRepository` (escritura atómica con archivo `.tmp`, `flush()` + `os.fsync()` y `os.replace()`, protegida por `threading.RLock` reentrante para permitir transacciones compuestas dentro de `with repo.atomic():` sin interbloqueo).
  - Implementó `src/lab_reservations/scripts/manage_data.py` con `init` (no destructivo) y `reset --confirm` (reemplazo atómico con advertencia explícita de borrado irreversible de reservas activas y canceladas).
  - Creó `tests/integration/test_json_persistence.py` cubriendo carga de las 5 unidades reales, supervivencia de reservas `ACTIVE` y `CANCELLED` al descartar y recrear el servicio sobre el mismo JSON, concurrencia local multihilo, detección de JSON corrupto y subcomandos `init`/`reset`.
- **Decisión humana (aceptar / corregir / rechazar) y motivo:** **Aceptado** tras revisar `json_repositories.py`, `manage_data.py` y las 33 pruebas aprobadas, validando el uso de `threading.RLock` para evitar interbloqueos en bloques `atomic()`, el reemplazo atómico `.tmp` + `os.replace()` sin borrado físico y la advertencia explícita en `reset --confirm`.
- **Evidencia verificable (commit / archivos / pruebas):** Commit `7371a93`; archivos [`src/lab_reservations/infrastructure/json_repositories.py`](../src/lab_reservations/infrastructure/json_repositories.py), [`src/lab_reservations/scripts/manage_data.py`](../src/lab_reservations/scripts/manage_data.py) y [`tests/integration/test_json_persistence.py`](../tests/integration/test_json_persistence.py).

### Episodio 3 — API HTTP REST local (`FastAPI`), evolución `v1.1` de especificación y pruebas E2E (`RF-01`..`RF-05`, `CA-01`..`CA-07`)
- **Objetivo y requisito:** Exponer la capa HTTP REST local en `src/lab_reservations/api/` con traducción determinista de excepciones de dominio a códigos HTTP (`200`, `201`, `404`, `409`, `422`), consolidar `docs/SPECIFICATION.md` a `v1.1` (registrando el refinamiento real de `SUP-05` a `threading.RLock` y el sobre uniforme de errores) y crear la suite integral de pruebas HTTP incluyendo reinicio de la aplicación (`tests/api/test_http_api.py`).
- **Contexto suministrado y extracto de instrucción:** Se suministraron `docs/SPECIFICATION.md`, `AGENTS.md`, `application/services.py` e `infrastructure/json_repositories.py`. Extracto de instrucción tras aprobar el Episodio 2: *"esta todo en orden, sigamos adelante."*
- **Acción / resultado del agente:**
  - Actualizó `docs/SPECIFICATION.md` a `v1.1` documentando el historial evolutivo respecto al commit inicial `7e80e4e`.
  - Implementó `src/lab_reservations/api/schemas.py` (`StrictStr`, `extra="forbid"`, sobre uniforme `ErrorEnvelope`) y `src/lab_reservations/api/app.py` con fábrica `create_app()` basada en `lifespan` (cero efectos en disco al importar el módulo y compatible directamente con `uvicorn lab_reservations.api.app:app`).
  - Al ejecutar `pytest`, detectó una advertencia real de deprecación en `starlette 1.10.0` (`HTTP_422_UNPROCESSABLE_ENTITY` -> `HTTP_422_UNPROCESSABLE_CONTENT` según RFC 9110) y ajustó `app.py` para usar `HTTP_422_UNPROCESSABLE_CONTENT` con fallback seguro.
  - Creó y ejecutó `tests/api/test_http_api.py` verificando sobre HTTP todos los criterios `CA-01`..`CA-07`, incluido el apagado y arranque de una nueva instancia `FastAPI` sobre el mismo directorio de datos (`39 passed` en total).
- **Decisión humana (aceptar / corregir / rechazar) y motivo:** **Aceptado** tras revisar la actualización `v1.1` de `SPECIFICATION.md`, la implementación HTTP en `api/` y ejecutar personalmente en terminal la suite completa de 39 pruebas y los comandos `manage_data init` y `manage_data reset --confirm`, comprobando que el inventario precargado permanece intacto.
- **Evidencia verificable (commit / archivos / pruebas):** Commit `32ac9f6`; archivos [`docs/SPECIFICATION.md`](SPECIFICATION.md), [`src/lab_reservations/api/app.py`](../src/lab_reservations/api/app.py), [`src/lab_reservations/api/schemas.py`](../src/lab_reservations/api/schemas.py) y [`tests/api/test_http_api.py`](../tests/api/test_http_api.py).

---

## 4. Registro de Verificaciones (Agente vs. Comprobación Humana)

Siguiendo la consigna, se distingue explícitamente lo ejecutado e informado por el agente dentro del *harness* respecto de las comprobaciones ejecutadas directamente por la persona responsable en su terminal local (`Windows`, `PowerShell`, `Python 3.12.0`, `pytest 8.4.2`, `fastapi 0.162.0`, `starlette 1.10.0`, `uvicorn 0.54.0`).

### 4.1 Ejecutado e informado por el agente (entorno de herramientas Antigravity)

| Etapa | Comando / Procedimiento | Versión observada | Resultado observado | Incidentes / ajustes reales |
| :--- | :--- | :--- | :--- | :--- |
| Verificación de entorno | `python --version; git --version; pip --version` | `Python 3.12.0`, `git 2.42.0.windows.2`, `pip 23.2.1` | Entorno base disponible; `uv` no instalado (se optó por `venv` + `requirements.lock.txt`). | Se reescribió `requirements.lock.txt` en UTF-8 sin BOM para evitar problemas de codificación en `pip` de Windows. |
| Episodio 1 (Unitarias) | `.\.venv\Scripts\python.exe -m pytest` | `pytest 8.4.2` | `28 passed in 0.24s` (`CA-01`..`CA-06`, invariantes `RN-01`..`RN-07`). | Ningún fallo. |
| Episodio 2 (Persistencia JSON + Reinicio) | `.\.venv\Scripts\python.exe -m pytest` | `pytest 8.4.2` | `33 passed in 9.14s` (incluye `CA-07` sobre archivos reales en disco, concurrencia multihilo y `manage_data`). | Durante la implementación previa a tests se reemplazó `unlink()` en `manage_data reset` por reemplazo atómico `JsonReservationRepository(..., reset=True)`. |
| Episodio 3 (API HTTP + Reinicio de App) | `.\.venv\Scripts\python.exe -m pytest` | `pytest 8.4.2`, `fastapi 0.162.0`, `starlette 1.10.0` | Primera corrida: `39 passed, 2 warnings`. Segunda corrida tras ajuste: `39 passed, 1 warning in 5.05s`. | Se corrigió `HTTP_422_UNPROCESSABLE_ENTITY` -> `HTTP_422_UNPROCESSABLE_CONTENT` (RFC 9110 en Starlette `1.10`). Quedó 1 *warning* interno de terceros en `fastapi.testclient` sobre `httpx`/`httpx2`. |

### 4.2 Comprobaciones realmente ejecutadas por la persona responsable

| Comprobación | Comando ejecutado | Entorno / Versión | Resultado esperado | Resultado realmente observado |
| :--- | :--- | :--- | :--- | :--- |
| Versión del intérprete virtual | `.\.venv\Scripts\python.exe --version` | `Python 3.12.0` (Windows) | Confirmar `Python 3.12.0` aislado en `.venv`. | `Python 3.12.0` verificado sin errores. |
| Suite automática completa (`CA-01`..`CA-07`) | `.\.venv\Scripts\python.exe -m pytest` | `Python 3.12.0`, `pytest 8.4.2` | Aprobar los 39 tests automáticos (dominio, persistencia JSON, concurrencia y reinicio HTTP). | 39 pruebas aprobadas en orden (`39 passed`). |
| Carga inicial segura de datos | `.\.venv\Scripts\python.exe -m lab_reservations.scripts.manage_data init` | `Python 3.12.0` | Validar `data/inventory.json` (5 unidades) y preparar `data/reservations.json` sin borrar historial previo. | Ejecución exitosa (`OK [init]`), 5 unidades verificadas. |
| Reinicio explícito de datos y resguardo de catálogo | `.\.venv\Scripts\python.exe -m lab_reservations.scripts.manage_data reset --confirm` | `Python 3.12.0` | Vaciar reservas con advertencia explícita y conservar intacto `data/inventory.json`. | Ejecución exitosa; `data/inventory.json` permaneció intacto con sus 5 unidades originales. |
| Levantamiento interactivo manual de `uvicorn` | *(Opcional; cubierto automáticamente por `test_http_api.py::test_http_app_restart_recovers_active_and_cancelled_reservations`)* | — | — | Paso manual interactivo opcional no requerido tras comprobar `CA-07` en pruebas automáticas; procedimiento reproducible documentado en `README.md`. |
