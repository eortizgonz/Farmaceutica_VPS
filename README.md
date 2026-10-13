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
