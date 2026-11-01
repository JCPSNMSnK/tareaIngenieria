# Sistema de Reservas de Equipamiento de Laboratorio

Solución local, determinista y verificable para la gestión de disponibilidad, reservas y cancelaciones con historial de unidades físicas de laboratorio, desarrollada aplicando prácticas de Ingeniería de Software asistida por un agente de programación bajo supervisión humana.

> **Estado actual del repositorio:** Fase inicial de especificación y preparación del agente completada. Implementación en progreso siguiendo los episodios planificados en [`docs/PROGRESS_AND_DECISIONS.md`](docs/PROGRESS_AND_DECISIONS.md).

---

## 1. Especificación breve

- **Problema y alcance:** Evitar reservas superpuestas sobre una misma unidad física y evitar que las cancelaciones sigan bloqueando horarios o pierdan trazabilidad histórica, operando sobre un inventario precargado fijo (`MIC-01`, `MIC-02`, `OSC-01`, `MUL-01`, `FUE-01`).
- **Reglas centrales:**
  - Unidad existente en inventario, solicitante ficticio no vacío ni de solo espacios, fechas/horas ISO locales válidas e `inicio < fin`.
  - Intervalos semiabiertos `[inicio, fin)`: rechaza superposiciones activas en la misma unidad, permite límites consecutivos (`10:00–11:00` y `11:00–12:00`) y permite reservas simultáneas en unidades distintas.
  - La cancelación conserva ID y datos (`CANCELLED`) y libera disponibilidad. La consulta de disponibilidad aplica exactamente las mismas reglas que la creación.
- **Especificación detallada, supuestos (`SUP-01`..`SUP-05`) y criterios de aceptación (`CA-01`..`CA-07`):** Ver [`docs/SPECIFICATION.md`](docs/SPECIFICATION.md).

---

## 2. Solución

- **Arquitectura:** Capas limpias ligeras en Python 3.12 (`domain`, `application`, `infrastructure`, `api`, `scripts`) con API HTTP REST local (`FastAPI`) y persistencia JSON atómica separando catálogo (`data/inventory.json`) y estado operativo (`data/reservations.json`).
- **Instalación, carga inicial, reinicio de datos, ejecución y pruebas:** *(Se completará al finalizar los episodios de implementación con comandos exactos, advertencias de borrado en reset y ejemplos reproducibles de entrada/salida).*

---

## 3. Preparación del agente

- **Entorno (Harness) y modelo:** Google Antigravity IDE sobre Windows, utilizando un único agente de programación con modelo Gemini (*Gemini 4 Argon (High)* seleccionado en la interfaz; identificador interno exacto de build/checkpoint no expuesto públicamente en la UI). La aplicación entregada no depende de modelos ni cuentas externas para ejecutarse ni probarse.
- **Instrucciones y adaptaciones específicas comprobables:**
  - Reglas globales del repositorio y semántica de intervalos semiabiertos `[start, end)`: [`AGENTS.md`](AGENTS.md).
  - Skill específica para persistencia JSON atómica, separación de archivos y prueba de reinicio: [`.agents/skills/persistence-verification/SKILL.md`](.agents/skills/persistence-verification/SKILL.md).
- **Retención de progreso y controles humanos:** Registro vivo versionado en [`docs/PROGRESS_AND_DECISIONS.md`](docs/PROGRESS_AND_DECISIONS.md), con revisión humana previa a cada commit.

---

## 4. Registro de decisiones y delegación

Las decisiones arquitectónicas y técnicas (`ADR-01` a `ADR-05`) junto con el registro trazable de los **tres episodios reales de delegación** y las **verificaciones ejecutadas** se documentan en [`docs/PROGRESS_AND_DECISIONS.md`](docs/PROGRESS_AND_DECISIONS.md) (y se sintetizarán aquí al cierre de la implementación).
