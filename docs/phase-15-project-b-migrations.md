# Fase 15 (Proyecto B) - Migraciones de modelo persistido

## Resumen
Se inicia la ruta con migraciones de base de datos para persistir el modelo explicito de verificacion en `CitaMedica`, sin eliminar aun campos legacy.

## Cambios aplicados
- Nuevos campos en `operations.CitaMedica`:
  - `estado_verificacion` (`PENDIENTE | VERIFICADA | NO_REQUERIDA`)
  - `metodo_verificacion` (`BIOMETRIA | QR | MANUAL | OTRO | ""`)
- Migracion de datos (`0017_citamedica_verification_fields`) para backfill de historico desde:
  - `estado`
  - `metodo_confirmacion`
- Sin eliminacion de `verif_biometria` ni `metodo_confirmacion` en esta etapa.

## Estrategia
1. **Expandir**: agregar columnas nuevas.
2. **Backfill**: poblar datos historicos.
3. **Dual-write temporal**: `save()` mantiene sincronia derivando campos nuevos desde legacy.
4. **Contraccion futura**: en una fase posterior se eliminan campos legacy cuando todo consumidor use los nuevos.

## Nota de despliegue
- Esta fase **si requiere migraciones**:
  - `python manage.py migrate`
