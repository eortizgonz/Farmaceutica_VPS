# Pharma & MedDev AI Copilot - UltraApp

Aplicación demo avanzada para procesos de Farmacéutica y Dispositivos Médicos.

## Qué incluye
- Dashboard 360 ejecutivo
- Mini apps integradas por proceso: Validación, Batch Records, Auditoría, Calidad y Regulación
- Semáforo dinámico por KPI
- Simuladores SAP: ERP, MII, ME, CAP y BTP
- Preguntas dinámicas por perfil: Operacional, Financiero, Ejecutivo y Comercial
- Centro de alertas, acciones sugeridas, cronograma y cockpit documental
- Diseño tipo cloud, profesional y centrado en UX

## Funcionalidades de acceso
- Registro de usuarios con nombre, correo, username y contraseña
- Contraseñas almacenadas con hash seguro
- Inicio de sesión por username o correo
- Sesión persistente opcional y cierre de sesión protegido con CSRF
- Dashboard disponible solamente para usuarios autenticados

## Configurar PostgreSQL
1. Copiar `.env.example` como `.env`.
2. Completar `POSTGRES_USER` y `POSTGRES_PASSWORD` con las credenciales locales.
3. Ajustar `POSTGRES_HOST`, `POSTGRES_PORT` y `POSTGRES_DB` si es necesario.
4. Generar un valor largo y aleatorio para `SECRET_KEY`.

El archivo `.env` está ignorado por Git y no debe compartirse ni subirse al repositorio.

## Ejecutar
```bash
pip install -r requirements.txt
flask --app app create-db
flask --app app db upgrade
python app.py
```
Luego abra `http://127.0.0.1:8000`

La primera visita redirige a `/login`; desde allí se puede crear el primer usuario.

## Cambios futuros de tablas
Después de modificar o agregar modelos:
```bash
flask --app app db migrate -m "descripción del cambio"
flask --app app db upgrade
```
Revise siempre la migración generada antes de ejecutar `db upgrade` en producción.

## Pruebas
```bash
python -m unittest discover -s tests -v
```

## Despliegue con Docker en un VPS

El archivo `compose.yaml` levanta dos servicios:

- `db`: PostgreSQL con datos persistentes en el volumen `postgres_data`.
- `app`: Flask servido por Gunicorn; aplica las migraciones antes de iniciar.

En el VPS:

```bash
git clone URL_DEL_REPOSITORIO
cd NOMBRE_DEL_REPOSITORIO
cp .env.docker.example .env
```

Edite `.env` y configure contraseñas únicas. Puede generar `SECRET_KEY` con:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Construya e inicie los contenedores:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

PostgreSQL crea la base indicada por `POSTGRES_DB` durante el primer arranque y
la aplicación ejecuta `flask db upgrade` automáticamente. El puerto predeterminado
de la app es `8010` y queda publicado en todas las interfaces del VPS para acceso
directo mediante `http://IP_DEL_VPS:8010`.

Comandos habituales:

```bash
docker compose pull
docker compose up -d --build
docker compose exec app python -m flask --app app db current
docker compose logs --tail=100 app
```

No elimine el volumen `postgres_data` durante una actualización: contiene la
base de datos. Antes de cambios importantes, realice una copia de seguridad.

## Recuperación de contraseña por Gmail

La pantalla de acceso permite solicitar un enlace de recuperación por correo.
El enlace firmado vence después de 60 minutos y se invalida al actualizar la
contraseña. La respuesta de la aplicación no revela si un correo está registrado.

Para utilizar Gmail active la verificación en dos pasos en la cuenta de Google y
genere una contraseña de aplicación. Configure en `.env`:

```text
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=su_cuenta@gmail.com
MAIL_PASSWORD=password_de_aplicacion_de_google
MAIL_DEFAULT_SENDER=su_cuenta@gmail.com
APP_BASE_URL=http://IP_DEL_VPS:8010
```

No utilice la contraseña normal de Gmail y no agregue `.env` al repositorio.

## Asistente SOP con Ollama y pgvector

Los usuarios autenticados pueden cargar documentos PDF, TXT o Markdown desde
`/sop` y realizar consultas documentales o troubleshooting guiado. PostgreSQL
con la extensión pgvector persiste los fragmentos y embeddings; Ollama genera
los vectores y las respuestas localmente.

El dashboard también incluye un chat flotante que consume el mismo flujo RAG
mediante el endpoint autenticado `POST /api/sop/chat`, con respuesta y fuentes.

La estructura, consultas SQL, acceso desde el VPS/DBeaver, eliminación controlada
y respaldos están documentados en [GUIA_PGVECTOR.md](GUIA_PGVECTOR.md).

Modelos requeridos:

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

En local se usa `http://127.0.0.1:11434`. En Docker, Compose conecta con el
Ollama del VPS mediante `http://host.docker.internal:11434`. Los vectores se
conservan junto con PostgreSQL en el volumen `postgres_data`.

El directorio `datos_simulados` incluye once documentos ficticios para probar
manuales de equipos, calidad, liberación de lotes y troubleshooting. Se cargan
en bloque con:

```bash
flask --app app ingest-documents datos_simulados
```

Dentro del contenedor del VPS use:

```bash
docker compose exec app python -m flask --app app ingest-documents datos_simulados
```

Estos documentos son únicamente datos de demostración y no sustituyen SOP
aprobados, instrucciones del fabricante ni decisiones de Calidad/EHS.

## Analítica predictiva de equipos

La ruta autenticada `/predictive` muestra 20 equipos, sus últimas lecturas y un
índice demostrativo de probabilidad de falla. El cálculo compara horas de uso,
vibración, temperatura, corriente, RPM y presión con los límites configurados
para cada máquina. Los estados son `Healthy` (menos de 40%), `Warning` (40% a
menos de 70%) y `Critical` (70% o más).

Después de aplicar las migraciones, cargue o restablezca los datos simulados:

```bash
flask --app app db upgrade
flask --app app seed-predictive-data
```

En Docker:

```bash
docker compose exec app python -m flask --app app seed-predictive-data
```

El índice es explicable y útil para demostración, pero no constituye un modelo
validado. Para uso real debe entrenarse y validarse con historial confiable de
lecturas, mantenimiento y fallas confirmadas.

### Construcción del historial de lecturas

El catálogo puede ejecutarse nuevamente sin eliminar el historial existente:

```bash
flask --app app seed-predictive-data
```

Para crear 90 días de historia con una lectura por hora:

```bash
flask --app app backfill-predictive-history --days 90 --interval-minutes 60
```

La carga retrospectiva solo completa el periodo anterior a la primera lectura,
por lo que repetir el comando no duplica el mismo intervalo. Para agregar una
nueva captura de las 20 máquinas:

```bash
flask --app app capture-machine-readings
```

Para observar cambios continuos en local, mantenga una segunda terminal abierta
con el recolector. El valor predeterminado es 15 segundos:

```bash
flask --app app run-reading-collector --interval-seconds 15
```

En Docker, el servicio `collector` ejecuta esta tarea automáticamente. El
intervalo se configura en `.env`; por defecto son 15 minutos:

```text
PREDICTIVE_CAPTURE_INTERVAL=900
```

Como alternativa puede utilizar `cron` (no active ambos mecanismos):

```cron
*/15 * * * * cd /ruta/Farmaceutica_VPS && /usr/bin/docker compose exec -T app python -m flask --app app capture-machine-readings >> /tmp/pharma-readings.log 2>&1
```

Se recomienda programar el comando externamente y no dentro de Flask/Gunicorn,
ya que varios workers podrían insertar capturas duplicadas. Los datos generados
son sintéticos; para entrenar un modelo supervisado también deben registrarse
fallas reales confirmadas y mantenimientos, no solo señales de sensores.

### Reglas del índice de riesgo

El índice combina vibración (25%), temperatura (20%), corriente (17%),
desviación de RPM (14%), horas de uso (12%) y presión (12%). Para cada variable,
el consumo del límite se transforma a una severidad: hasta 60% no aporta riesgo;
de 60% a 80% aporta hasta 25 puntos; de 80% a 100% aporta entre 25 y 70; y de
100% a 115% aporta entre 70 y 100. Un valor sobre 115% fuerza al menos 75% de
riesgo, dos límites excedidos fuerzan al menos 70% y uno fuerza al menos 45%.

Cuando se cambien estas reglas, todo el historial se actualiza sin regenerarlo:

```bash
flask --app app recalculate-machine-risks
```

La pantalla `/predictive` consulta el endpoint autenticado
`GET /api/predictive/snapshot` cada 15 segundos. Al aparecer nuevas lecturas,
actualiza sin recargar la página los conteos por estado, riesgo promedio, activo
prioritario, variables, porcentajes y explicaciones. El botón `Actualizar`
permite solicitar una lectura inmediata de la base de datos.

### Chat de analítica predictiva

El chat incluye el modo `Analítica predictiva`. Este modo no permite que el
modelo genere SQL: la aplicación ejecuta consultas controladas sobre `machines`
y `machine_readings` y entrega a Ollama el resumen actual, los cinco equipos de
mayor riesgo, reglas del índice y tendencias de 24 horas para las máquinas
mencionadas. Las respuestas identifican PostgreSQL y la fecha de lectura como
fuente, y distinguen el índice demostrativo de una probabilidad validada.
