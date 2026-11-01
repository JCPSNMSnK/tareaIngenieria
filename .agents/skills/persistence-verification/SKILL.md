---
name: persistence-verification
description: >-
  Protocolo obligatorio para implementar y verificar la persistencia JSON atómica,
  la separación entre inventario precargado y reservas, el comando de reinicio de datos
  y la prueba de recuperación de reservas activas y canceladas tras reiniciar la aplicación.
  Usar siempre que se trabaje en infraestructura de datos, scripts de datos o pruebas de persistencia.
---

# Protocolo de Persistencia JSON Atómica y Verificación de Reinicio

Seguir exactamente estos pasos al implementar o auditar la persistencia del sistema de reservas:

## 1. Separación estricta de archivos de datos
1. **`data/inventory.json` (Solo lectura, versionado en Git):**
   - Contiene exclusivamente las 5 unidades físicas precargadas (`MIC-01`, `MIC-02`, `OSC-01`, `MUL-01`, `FUE-01`).
   - El código de aplicación **nunca** escribe ni modifica este archivo.
2. **`data/reservations.json` (Lectura/escritura, estado operativo):**
   - Estructura JSON explícita con versión de esquema, contador secuencial (`next_sequence`) y lista `reservations`.
   - Si el archivo no existe al iniciar el repositorio, crearlo automáticamente con `{"schema_version": 1, "next_sequence": 1, "reservations": []}` **sin** sobrescribir si ya existe.

## 2. Escritura atómica y seguridad local
1. Proteger lecturas-modificaciones-escrituras con un `threading.Lock` en `JsonReservationRepository`.
2. Nunca abrir `data/reservations.json` directamente en modo truncado (`"w"`) para escribir en caliente:
   - Escribir primero el JSON serializado (UTF-8, indentado legible) en un archivo temporal en el mismo directorio (`reservations.json.tmp`) y hacer `flush()` + `os.fsync()`.
   - Reemplazar atómicamente el archivo destino mediante `os.replace(tmp_path, target_path)`.

## 3. Comando de carga inicial y reinicio de datos (`manage_data`)
- Proveer dos subcomandos explícitos:
  - `init`: Verifica que `data/inventory.json` sea válido e inicializa `data/reservations.json` solo si no existe (operación segura que **no borra** reservas existentes).
  - `reset --confirm`: Restablece `data/reservations.json` al estado vacío inicial conservando `data/inventory.json`. Debe exigir `--confirm` y emitir una advertencia explícita indicando que **borra todas las reservas activas y canceladas**.

## 4. Verificación obligatoria de supervivencia al reinicio (`CA-07`)
Toda suite de pruebas debe incluir un test automático que verifique el ciclo completo sobre un archivo real en disco (`tmp_path`):
1. Instanciar aplicación/servicio #1 apuntando a `reservations.json`.
2. Crear al menos dos reservas válidas (`RES-0001` y `RES-0002`).
3. Cancelar `RES-0001` (queda `CANCELLED`) y mantener `RES-0002` en `ACTIVE`.
4. Destruir/descartar por completo la instancia #1 en memoria y crear una **nueva instancia #2** apuntando al mismo `reservations.json` y `inventory.json` sin ejecutar `reset`.
5. Comprobar en la instancia #2 que:
   - `RES-0001` sigue existiendo con todos sus datos originales y estado `CANCELLED`, y su intervalo está **disponible** (`available == True`).
   - `RES-0002` sigue existiendo con estado `ACTIVE`, y su intervalo sigue **bloqueado** (`available == False`).
   - Crear una tercera reserva genera `RES-0003` sin colisionar identificadores anteriores.
