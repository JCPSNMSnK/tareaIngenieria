# Progreso del Proyecto, Decisiones de Ingeniería y Delegación

Este documento versionado conserva el estado operativo del proyecto, el registro de decisiones arquitectónicas y técnicas (ADRs), la trazabilidad de los episodios reales de delegación al agente de programación y el registro de verificaciones ejecutadas.

---

## 1. Estado de Progreso

- [x] **Fase 1:** Inicialización del repositorio Git (`main`), `.gitignore` e inventario inicial (`data/inventory.json`).
- [x] **Fase 2:** Redacción y aprobación humana de la Especificación Inicial v1.0 (`docs/SPECIFICATION.md`).
- [x] **Fase 3:** Preparación y aprobación humana del agente (`AGENTS.md` + `.agents/skills/persistence-verification/SKILL.md`) y decisiones iniciales (`ADR-01`..`ADR-05`).
- [x] **Fase 4 — Episodio 1 de delegación:** Capa de dominio (`domain/`) y capa de aplicación (`application/`) con pruebas unitarias puras.
- [x] **Fase 4 — Episodio 2 de delegación:** Persistencia JSON atómica (`infrastructure/`), comando `manage_data` (`scripts/`) y pruebas de persistencia/reinicio.
- [ ] **Fase 4 — Episodio 3 de delegación:** API HTTP REST local con FastAPI (`api/`) y suite integral de pruebas automáticas (`tests/`).
- [ ] **Fase 5:** Ejecución y registro de verificaciones humanas reproducibles (automáticas + prueba manual de reinicio).
- [ ] **Fase 6:** Cierre documental del `README.md` y auditoría final del repositorio.

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
- **Decisión:** Persistir el catálogo inmutable en `data/inventory.json` (solo lectura, versionado) y el historial de reservas en `data/reservations.json` (lectura/escritura con archivo temporal + `os.replace` y `threading.Lock`).
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
- **Evidencia verificable (commit / archivos / pruebas):** Archivos [`src/lab_reservations/infrastructure/json_repositories.py`](../src/lab_reservations/infrastructure/json_repositories.py), [`src/lab_reservations/scripts/manage_data.py`](../src/lab_reservations/scripts/manage_data.py) y [`tests/integration/test_json_persistence.py`](../tests/integration/test_json_persistence.py).

### Episodio 3 — Pendiente
- **Objetivo y requisito:** *Por ejecutar.*
- **Contexto suministrado y extracto de instrucción:** *Por ejecutar.*
- **Acción / resultado del agente:** *Por ejecutar.*
- **Decisión humana (aceptar / corregir / rechazar) y motivo:** *Por ejecutar.*
- **Evidencia verificable (commit / archivos / pruebas):** *Por ejecutar.*

---

## 4. Registro de Verificaciones (Agente vs. Comprobación Humana)

*(Se completará en la Fase 5 distinguiendo lo reportado por el agente de los comandos realmente ejecutados y observados).*
