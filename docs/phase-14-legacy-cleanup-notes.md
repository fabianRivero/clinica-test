# Fase 14 - Limpieza residual de terminologia y contrato

## Fecha
- 2026-05-21

## Alcance aplicado
- Se revisaron textos de UI para evitar referencias legacy donde el contexto es estado general de verificacion.
- Se mantuvo el uso de "biometria" solo cuando representa metodo de verificacion o flujos biométricos especificos.

## Ajustes realizados
- Portal cliente (agenda): descripcion cambiada de "cierre biometrico" a "cierre de verificacion".
- Admin cliente (sesiones): descripcion cambiada de "validacion biometrica" a "verificacion registrada".

## Criterio de lenguaje
- **Verificacion**: estado/proceso general.
- **Biometria**: metodo especifico de verificacion.

## Pendientes recomendados (opcional)
- Revisar claves de analytics legacy (por ejemplo IDs con sufijo `-biometric`) y decidir plan de renombre controlado.
- Revisar nombres internos de funciones/rutas que incluyen `biometric` para decidir si se mantiene por compatibilidad o se versiona.
