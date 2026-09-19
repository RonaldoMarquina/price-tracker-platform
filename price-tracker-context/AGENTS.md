# Instrucciones para agentes de IA

## Fuente de verdad

Antes de modificar código, leer en este orden:

1. `README.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/REQUIREMENTS.md`
4. `docs/ARCHITECTURE.md`
5. El documento específico del módulo que se modificará.

Si el código contradice estos documentos, informar la diferencia antes de cambiar la arquitectura.

## Reglas obligatorias

- Trabajar únicamente en la tarea solicitada.
- No sustituir React, FastAPI, PostgreSQL, SQS ni ECS Fargate sin autorización.
- No convertir el proyecto en una colección de microservicios.
- No ejecutar scraping dentro de una solicitud HTTP de la API.
- No conectar el frontend directamente con PostgreSQL ni con SQS.
- No guardar contraseñas, tokens o claves en el repositorio.
- No asumir que UUID proporciona seguridad o autorización.
- No introducir Redis, Kubernetes, WAF, réplicas de lectura o Multi-AZ durante el MVP.
- No crear funcionalidades de usuarios, pagos, recomendaciones o inteligencia artificial que no estén en los requisitos.
- No realizar operaciones destructivas sin explicar el objetivo y solicitar confirmación.

## Forma de trabajar

1. Revisar el contexto y el código relacionado.
2. Proponer un plan breve.
3. Implementar el cambio mínimo necesario.
4. Ejecutar formateo, pruebas y análisis estático.
5. Informar archivos modificados, pruebas ejecutadas y asuntos pendientes.

## Calidad

- Usar nombres claros en inglés para código y nombres comprensibles en español para la interfaz.
- Mantener funciones pequeñas y responsabilidades separadas.
- Validar toda entrada externa.
- Usar consultas parametrizadas mediante el ORM.
- Diseñar los workers para que sean idempotentes.
- Registrar eventos importantes sin incluir secretos ni información sensible.
- Agregar pruebas para reglas de negocio y endpoints nuevos.
- Actualizar la documentación cuando cambie un contrato o decisión técnica.

## Criterio de terminado

Una tarea se considera terminada cuando:

- Cumple los criterios de aceptación.
- No rompe pruebas existentes.
- Incluye manejo básico de errores.
- No contiene secretos ni valores locales fijos.
- Los comandos para verificarla están documentados.

