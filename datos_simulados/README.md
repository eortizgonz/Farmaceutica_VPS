# Documentos simulados para pruebas RAG

Contenido completamente ficticio para validar Ollama + pgvector. No representa
instrucciones de ningún fabricante ni sustituye SOP aprobados, evaluación de
riesgos, bloqueo/etiquetado, QA, EHS o personal técnico autorizado.

Archivos:

- `SOP-EQP-001_empacadora_blister.md`
- `SOP-EQP-002_mezcladora_alto_cizallamiento.md`
- `SOP-EQP-003_reactor_r500.md`
- `SOP-CAL-004_desviaciones_capa.md`
- `GUIA-LOT-005_tabletas_liberacion.md`
- `PROC-OP-006_ciclo_orden_produccion.md`
- `ORD-PROD-2026-001_lote_A10-26001.md`
- `SOP-EQP-007_tableteadora_CT900.md`
- `SOP-EQP-008_recubridora_RC600.md`
- `SOP-PRO-009_despeje_linea_cambio_producto.md`
- `SOP-LOG-010_materiales_trazabilidad.md`

Carga masiva:

```bash
flask --app app ingest-documents datos_simulados
```
