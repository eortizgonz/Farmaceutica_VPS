# SIMULADO — PROC-OP-006 Ciclo de una orden de producción

Versión 1.0. Información ficticia para pruebas del asistente.

## Estados y responsables

Planificación crea la orden en estado Borrador y asigna producto, fórmula, cantidad y fecha. Producción solo puede ejecutar una orden Liberada. QA revisa fórmula, materiales, equipos y documentos y cambia el estado a Liberada. Al comenzar el pesaje pasa a En proceso. Una desviación crítica, material rechazado o resultado fuera de especificación cambia la orden a Retenida. Solo QA puede cambiarla a Liberada para despacho o Rechazada.

## Preparación

Antes de iniciar, el supervisor confirma orden y versión de fórmula, disponibilidad y vigencia de materiales, capacitación del personal, calibración de instrumentos, estado limpio de equipos y despeje de línea aprobado. Cada material se verifica por código, lote, caducidad y cantidad contra la lista de materiales.

## Ejecución y registro

Los tiempos, parámetros, cantidades reales, controles en proceso y firmas se registran al momento de la actividad. No se permiten espacios en blanco ni registros anticipados. Una corrección conserva el dato original, incluye motivo, fecha y firma. Los parámetros fuera de receta requieren detener la etapa y avisar a QA.

## Cierre

Producción reconcilia materiales y unidades, adjunta registros de limpieza y controles y entrega el expediente. QA verifica integridad de datos, resultados QC, desviaciones y rendimiento. Una orden no puede cerrarse con campos críticos incompletos, desviaciones sin evaluación o diferencias no explicadas.
