# Especificación del Sistema de Reservas de Laboratorio (v1.0)

## 1. Problema de Negocio
La coordinación de un laboratorio registra pedidos de equipamiento mediante mensajes y una planilla manual. Este proceso provoca dos fallas operativas recurrentes:
1. Confirmación accidental de una misma unidad física en horarios superpuestos.
2. Cancelaciones que siguen bloqueando el horario disponible o que, al borrarse manualmente, hacen perder el historial de solicitudes.

Se requiere un sistema local, determinista y verificable que permita consultar el inventario precargado, verificar disponibilidad por unidad e intervalo horario, registrar reservas identificables y cancelarlas liberando el horario sin eliminar su registro histórico, conservando el estado tras reiniciar la aplicación.

---

## 2. Alcance y Límites

### Dentro del alcance
- Lectura del inventario físico precargado de 5 unidades.
- Consulta de disponibilidad por unidad e intervalo temporal aplicando exactamente las mismas validaciones y reglas de conflicto que la creación.
- Creación de reservas individuales (una unidad por reserva) con identificador único, solicitante ficticio válido e intervalo `[inicio, fin)`.
- Cancelación lógica (*soft-cancel*) que preserva identificador y datos originales y libera inmediatamente el intervalo horario.
- Consulta de reservas (historial de activas y canceladas).
- Persistencia local en archivo JSON recuperable tras detener y reiniciar el proceso.
- Exposición mediante una API HTTP REST local reproducible sin cuentas de modelos ni servicios externos.

### Fuera de alcance
- Administración (alta, baja o modificación) del inventario precargado.
- Reservas multi-unidad en una sola transacción.
- Autenticación, autorización y roles de usuario reales.
- Notificaciones por correo/mensajería, pagos o integraciones externas.
- Interfaz gráfica compleja (web SPA/móvil), despliegue en nube, concurrencia distribuida multiproceso y escalabilidad de producción.

---

## 3. Inventario Precargado Fijo

Cada `id` identifica una unidad física distinta e independiente:

| ID de unidad | Equipo |
| :--- | :--- |
| `MIC-01` | Microscopio digital |
| `MIC-02` | Microscopio digital |
| `OSC-01` | Osciloscopio |
| `MUL-01` | Multímetro |
| `FUE-01` | Fuente de alimentación |

---

## 4. Requisitos Funcionales (`RF`)

- **`RF-01` — Lectura de inventario:** El sistema debe cargar el catálogo precargado desde `data/inventory.json` y permitir listar las unidades disponibles con su `id` y `name`.
- **`RF-02` — Consulta de disponibilidad:** Dado un `unit_id`, una fecha-hora `start` y una fecha-hora `end`, el sistema debe validar los parámetros con las reglas del dominio e informar si la unidad está disponible en ese intervalo.
- **`RF-03` — Creación de reserva:** Dados `unit_id`, `requester`, `start` y `end`, si se cumplen todas las reglas de validación y disponibilidad, el sistema debe crear una reserva en estado `ACTIVE` asignándole un identificador único secuencial legible (`RES-0001`, `RES-0002`, ...).
- **`RF-04` — Cancelación de reserva con historial:** Dado el `id` de una reserva existente en estado `ACTIVE`, el sistema debe cambiar su estado a `CANCELLED` conservando intactos su identificador, unidad, solicitante e intervalo original, y liberando dicho intervalo para futuras consultas y reservas.
- **`RF-05` — Persistencia y consulta de historial:** El sistema debe persistir todas las reservas (`ACTIVE` y `CANCELLED`) en almacenamiento local (`data/reservations.json`), recuperarlas íntegras al reiniciar la aplicación y permitir consultar el listado o detalle de reservas.

---

## 5. Reglas de Negocio e Invariantes (`RN`)

- **`RN-01` — Unidad conocida:** Toda operación de disponibilidad o reserva debe referenciar un `unit_id` exactamente presente en el inventario precargado (*case-sensitive*, sin espacios adicionales). Si no existe, se rechaza la solicitud.
- **`RN-02` — Solicitante válido y ficticio:** El campo `requester` se normaliza recortando espacios extremos (`strip()`). No puede ser vacío ni estar compuesto únicamente por espacios en blanco. Solo deben utilizarse nombres ficticios en pruebas y demostraciones.
- **`RN-03` — Intervalo temporal estricto (`start < end`):** Tanto `start` como `end` deben ser fechas y horas ISO válidas y `start` debe ser estrictamente anterior a `end` (duración mayor a cero). Si `start == end` o `start > end`, se rechaza.
- **`RN-04` — Semántica de intervalos semiabiertos `[start, end)` y turnos consecutivos:** Dos intervalos `[A.start, A.end)` y `[B.start, B.end)` se superponen si y solo si:
  `A.start < B.end` **y** `B.start < A.end`.
  - Una reserva `ACTIVE` bloquea su intervalo en esa unidad física.
  - Se rechaza cualquier superposición parcial o total con otra reserva `ACTIVE` de la **misma** unidad (ej. `10:00–11:00` rechaza `10:30–11:30`).
  - Se **permiten límites consecutivos** en la misma unidad cuando el fin de una coincide exactamente con el inicio de otra (`10:00–11:00` permite `11:00–12:00`).
  - Se **permiten reservas simultáneas** en unidades físicas distintas (ej. `MIC-01` y `MIC-02` reservadas ambas de `10:00` a `11:00`).
- **`RN-05` — Efecto de cancelación sobre disponibilidad:** Una reserva en estado `CANCELLED` permanece en el historial pero **no bloquea** disponibilidad para su unidad e intervalo.
- **`RN-06` — Transición de cancelación:** Solo una reserva existente puede cancelarse. Si el `id` no existe, se informa recurso no encontrado; si ya estaba en estado `CANCELLED`, se rechaza por conflicto de estado sin alterar sus datos.
- **`RN-07` — Simetría de reglas en disponibilidad:** La consulta de disponibilidad (`RF-02`) utiliza exactamente las mismas validaciones de unidad (`RN-01`), formato/orden de fechas (`RN-03`), lógica de solapamiento (`RN-04`) e ignorado de canceladas (`RN-05`) que la creación de reservas.

---

## 6. Supuestos Explícitos (`SUP`)

- **`SUP-01` — Zona horaria y formato de fechas:** El laboratorio opera físicamente en una única ubicación con hora local uniforme (`America/Argentina/Buenos_Aires`, `UTC-3`). Las entradas y salidas usan formato ISO-8601 local con fecha y hora obligatorias (`YYYY-MM-DDTHH:MM` o `YYYY-MM-DDTHH:MM:SS`, sin offset explícito / *timezone-naive* uniforme). Se rechazan entradas que contengan únicamente fecha (`YYYY-MM-DD`) o que incluyan offsets horarios heterogéneos (`Z`, `+02:00`), evitando ambigüedades de comparación.
- **`SUP-02` — Tratamiento de fechas pasadas:** Se permite operar sobre cualquier fecha y hora calendáricamente válida que cumpla `start < end`, sin restringir respecto al reloj actual del sistema. Esto permite registrar operaciones administrativas atemporales y garantiza que los tests y ejemplos documentados en el `README.md` sean 100 % deterministas y reproducibles en cualquier fecha futura de evaluación.
- **`SUP-03` — Límites de duración y anticipación:** No se aplican topes máximos de duración ni ventanas de anticipación; la única restricción temporal sobre el rango es `start < end`.
- **`SUP-04` — Persistencia separada de inventario y reservas:** El inventario vive en `data/inventory.json` (versionado, solo lectura) y las reservas en `data/reservations.json` (generado automáticamente vacío si no existe al iniciar, actualizado mediante escritura atómica por archivo temporal y reemplazo). Un comando explícito de reinicio de datos permite vaciar `data/reservations.json` conservando intacto `data/inventory.json`.
- **`SUP-05` — Concurrencia local:** Se protege el acceso concurrente dentro del mismo proceso local mediante `threading.Lock` en el repositorio JSON.

---

## 7. Contrato Preliminar de la API HTTP REST Local

- `GET /units` → `200 OK`: Lista las 5 unidades del inventario precargado.
- `GET /availability?unit_id={id}&start={iso}&end={iso}` → `200 OK`: Retorna disponibilidad booleana (y eventuales IDs activos en conflicto); retorna error si `unit_id` no existe (`404`) o si las fechas/rango son inválidos (`422`).
- `POST /reservations` → `201 Created`: Crea una reserva `ACTIVE`. Retorna `404` si la unidad no existe, `422` ante solicitante/fechas/intervalo inválidos y `409 Conflict` si existe superposición activa en esa unidad.
- `GET /reservations` → `200 OK`: Lista el historial completo de reservas (`ACTIVE` y `CANCELLED`), con filtro opcional por `unit_id` o `status`.
- `GET /reservations/{reservation_id}` → `200 OK` / `404 Not Found`: Obtiene el detalle de una reserva específica por ID.
- `POST /reservations/{reservation_id}/cancel` → `200 OK`: Cancela la reserva conservando ID y datos (`status = "CANCELLED"`). Retorna `404` si no existe o `409 Conflict` si ya estaba cancelada.

---

## 8. Criterios de Aceptación Verificables (`CA`)

- **`CA-01` (Creación válida):** Dado `MIC-01` sin reservas activas de `10:00` a `11:00`, cuando `"Dra. Valeria Méndez"` solicita ese intervalo, entonces se crea una reserva con ID único en estado `ACTIVE` y la consulta de disponibilidad para ese mismo rango informa `available = false`.
- **`CA-02` (Rechazo de superposición):** Dada una reserva `ACTIVE` en `MIC-01` de `10:00` a `11:00`, cuando otro solicitante intenta reservar `MIC-01` de `10:30` a `11:30` (o en cualquier rango con intersección no vacía), entonces el sistema rechaza la operación con conflicto (`409`) y no persiste la nueva reserva.
- **`CA-03` (Límites consecutivos permitidos):** Dada una reserva `ACTIVE` en `MIC-01` de `10:00` a `11:00`, cuando se consulta disponibilidad o se crea una reserva en `MIC-01` de `11:00` a `12:00` (o de `09:00` a `10:00`), entonces el sistema la acepta como disponible y válida.
- **`CA-04` (Unidades distintas simultáneas):** Dada una reserva `ACTIVE` en `MIC-01` de `10:00` a `11:00`, cuando se solicita `MIC-02` de `10:00` a `11:00`, entonces el sistema informa disponibilidad positiva y permite crear la reserva.
- **`CA-05` (Entradas inválidas):** Cuando se consulta disponibilidad o se intenta reservar con unidad inexistente (`MIC-99`), solicitante vacío (`""`) o de solo espacios (`"   "`), cadena de fecha malformada, fecha sin hora, fecha con timezone explícito, `start == end` o `start > end`, entonces el sistema rechaza la petición con error de cliente (`404` / `422`) tanto en creación como en disponibilidad (cuando aplique).
- **`CA-06` (Cancelación conserva historial y libera horario):** Dada una reserva `ACTIVE` en `MIC-01` de `10:00` a `11:00`, cuando se cancela por su ID, entonces el registro sigue accesible con su mismo ID y datos en estado `CANCELLED`, la disponibilidad de `MIC-01` de `10:00` a `11:00` pasa a `true` y puede crearse una nueva reserva activa en ese horario.
- **`CA-07` (Persistencia tras reinicio):** Dadas al menos una reserva `ACTIVE` y una reserva `CANCELLED` persistidas en `data/reservations.json`, cuando se detiene la instancia de la aplicación y se inicia una nueva instancia apuntando al mismo archivo sin borrar datos, entonces ambas reservas se recuperan con sus IDs, datos y estados originales intactos.
