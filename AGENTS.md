# Reglas del Agente de Programación — Sistema de Reservas de Laboratorio

Este archivo define las reglas operativas, restricciones de arquitectura, controles de supervisión humana y adaptaciones de dominio obligatorias para el agente de programación en este repositorio (cargado automáticamente por Google Antigravity).

## 1. Fuente de Verdad y Alcance
- La fuente de verdad funcional es `docs/SPECIFICATION.md`. Ningún cambio de código puede contradecir `RF-01`..`RF-05`, `RN-01`..`RN-07` ni `SUP-01`..`SUP-05`.
- Si surge una ambigüedad o cambio de alcance, primero debe proponerse y aprobarse el cambio en `docs/SPECIFICATION.md` y registrarse en `docs/PROGRESS_AND_DECISIONS.md` antes de implementarlo.
- **Fuera de alcance estricto:** No agregar autenticación, roles, bases de datos externas, colas, frontend gráfico complejo, llamadas a modelos LLM en tiempo de ejecución ni despliegue en la nube. La aplicación y sus pruebas deben ejecutarse 100 % en local sin cuentas externas.

## 2. Privacidad, Seguridad e Higiene de Datos
- **Prohibido** incluir nombres, correos, legajos o datos reales de personas/estudiantes en código, pruebas, ejemplos o commits. Usar exclusivamente solicitantes ficticios explícitos (ej. `"Dra. Valeria Méndez (Ficticio)"`, `"Ing. Martín Rojas (Ficticio)"`).
- **Prohibido** guardar tokens, credenciales, claves privadas o transcripciones crudas completas de conversaciones en el repositorio.

## 3. Arquitectura Obligatoria (Capas Limpias Ligeras)
Mantener separación estricta de dependencias (`api` / `infrastructure` -> `application` -> `domain`):
- `src/lab_reservations/domain/`: Entidades, objetos de valor, estados y excepciones del negocio. **Cero dependencias** de FastAPI, Pydantic, HTTP o sistema de archivos.
- `src/lab_reservations/application/`: Casos de uso (`ReservationService`) y contratos/protocolos de repositorios (`InventoryRepository`, `ReservationRepository`).
- `src/lab_reservations/infrastructure/`: Adaptadores JSON locales (`JsonInventoryRepository`, `JsonReservationRepository`).
- `src/lab_reservations/api/`: Aplicación FastAPI, esquemas HTTP y traducción determinista de excepciones de dominio a códigos HTTP (`404`, `409`, `422`).
- `src/lab_reservations/scripts/`: Comandos locales explícitos para inicialización y reinicio controlado de datos.

## 4. Adaptaciones Específicas de Dominio (Obligatorias y Comprobables)

### Adaptación A: Semántica de intervalos semiabiertos `[start, end)` y turnos consecutivos
- Todo rango horario debe representarse mediante un único objeto de valor `TimeInterval(start, end)` en `domain/`.
- Validar en construcción que `start` y `end` tengan fecha y hora explícitas, sean *timezone-naive* uniformes (hora local del laboratorio) y cumplan estrictamente `start < end`.
- Implementar la detección de superposición exclusivamente con la fórmula de intervalo semiabierto `[start, end)`:
  `self.start < other.end and other.start < self.end`
- Consecuencia obligatoria: dos reservas consecutivas donde `primera.end == segunda.start` (ej. `10:00`–`11:00` y `11:00`–`12:00`) **NO se superponen** y deben permitirse en la misma unidad.
- **Simetría obligatoria (`RN-07`):** Tanto `check_availability` como `create_reservation` deben validar la unidad y construir `TimeInterval` mediante la misma ruta lógica del dominio, garantizando idéntico comportamiento ante entradas inválidas, turnos consecutivos y reservas canceladas.

### Adaptación B: Cancelación lógica inmutable y persistencia JSON atómica
- **Prohibido eliminar físicamente registros de reservas** al cancelar. Cancelar transiciona el estado `ACTIVE` -> `CANCELLED` preservando `id`, `unit_id`, `requester`, `start`, `end` y `created_at` (agregando `cancelled_at`).
- Para implementar o verificar la persistencia y recuperación tras reinicio, activar y seguir la skill del proyecto en `.agents/skills/persistence-verification/SKILL.md`.

## 5. Controles Humanos y Retención de Progreso
- Trabajar en episodios acotados de delegación. No realizar commits en Git sin revisión y confirmación explícita del desarrollador humano responsable.
- Mantener actualizado `docs/PROGRESS_AND_DECISIONS.md` registrando decisiones técnicas, episodios de delegación y distinción estricta entre verificaciones ejecutadas por el agente y comprobaciones ejecutadas o validadas por la persona responsable.
