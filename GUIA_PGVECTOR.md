# Guía operativa de PostgreSQL y pgvector

## Estructura

La extensión `vector` se habilita mediante la migración Alembic
`c41f6d2e85b7_add_pgvector_sop_chunks.py`. La tabla principal es `sop_chunks`:

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | integer | Identificador del fragmento |
| `document_hash` | varchar(64) | SHA-256 del archivo original |
| `document_name` | varchar(255) | Nombre del documento cargado |
| `page` | integer | Página de origen |
| `chunk_index` | integer | Posición del fragmento en la página |
| `content` | text | Texto utilizado como contexto |
| `embedding` | vector(768) | Vector generado por `nomic-embed-text` |
| `created_at` | timestamptz | Fecha de indexación |

El índice `ix_sop_chunks_embedding_hnsw` acelera búsquedas por distancia coseno.

## Acceder desde el VPS

Abrir una sesión SQL dentro del contenedor:

```bash
docker compose exec db psql -U pharma_app -d pharma_copilot
```

Dentro de `psql`, los comandos más útiles son:

```sql
\dx vector
\d+ sop_chunks
\di+ ix_sop_chunks_embedding_hnsw
```

Salir con:

```sql
\q
```

## Consultas de inspección

Cantidad total de fragmentos:

```sql
SELECT count(*) AS total_fragmentos FROM sop_chunks;
```

Documentos indexados:

```sql
SELECT document_name,
       count(*) AS fragmentos,
       count(DISTINCT page) AS paginas,
       min(created_at) AS indexado_en
FROM sop_chunks
GROUP BY document_hash, document_name
ORDER BY indexado_en DESC;
```

Vista previa sin imprimir el vector completo:

```sql
SELECT id, document_name, page, chunk_index,
       left(content, 180) AS contenido
FROM sop_chunks
ORDER BY id DESC
LIMIT 20;
```

Comprobar dimensiones:

```sql
SELECT id, vector_dims(embedding) AS dimensiones
FROM sop_chunks
LIMIT 5;
```

## Búsqueda vectorial

La aplicación genera el vector de la pregunta con Ollama y ejecuta una consulta
equivalente a:

```sql
SELECT document_name, page, content,
       embedding <=> CAST(:query_embedding AS vector) AS distancia_coseno
FROM sop_chunks
ORDER BY embedding <=> CAST(:query_embedding AS vector)
LIMIT 5;
```

`<=>` calcula distancia coseno: los valores menores son resultados más cercanos.
No es práctico escribir manualmente un vector de 768 dimensiones; normalmente
la consulta debe realizarse desde la aplicación o un script que llame a Ollama.

## Acceso desde DBeaver

La base del contenedor no publica el puerto `5432` al VPS por seguridad. Para
conectarse desde DBeaver se recomienda un túnel SSH:

1. Crear una conexión PostgreSQL en DBeaver.
2. En la pestaña SSH, configurar el host y usuario del VPS.
3. Publicar temporalmente PostgreSQL solo en loopback o utilizar un túnel hacia
   el contenedor según la red Docker del servidor.
4. Usar la base `pharma_copilot` y el usuario definido en `.env`.

No se recomienda publicar PostgreSQL como `0.0.0.0:5432`.

## Eliminación controlada de un documento

Identificar primero el hash:

```sql
SELECT DISTINCT document_hash, document_name
FROM sop_chunks
ORDER BY document_name;
```

Después, dentro de una transacción:

```sql
BEGIN;
DELETE FROM sop_chunks WHERE document_hash = 'HASH_CONFIRMADO';
-- COMMIT;   -- confirmar
-- ROLLBACK; -- cancelar
```

## Respaldo y restauración

Respaldar toda la base desde el VPS:

```bash
docker compose exec -T db pg_dump -U pharma_app -d pharma_copilot > pharma_backup.sql
```

Restaurar sobre una base vacía y compatible con pgvector:

```bash
docker compose exec -T db psql -U pharma_app -d pharma_copilot < pharma_backup.sql
```

Los embeddings forman parte del respaldo PostgreSQL; no existe un volumen
vectorial separado.

## Diagnóstico

Versión instalada de pgvector:

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

Estado de la migración:

```bash
docker compose exec app python -m flask --app app db current
```

Modelos Ollama necesarios:

```bash
ollama list
```

Deben aparecer `llama3.1:8b` y `nomic-embed-text`.
