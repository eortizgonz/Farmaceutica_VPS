# Guía de ejecución
1. Instalar Python 3.10+ y PostgreSQL.
2. Crear y activar un entorno virtual de Python.
3. Instalar dependencias con `pip install -r requirements.txt`.
4. Copiar `.env.example` como `.env` y configurar las credenciales y `SECRET_KEY`.
5. Crear la base con `flask --app app create-db`.
6. Crear o actualizar las tablas con `flask --app app db upgrade`.
7. Ejecutar `python app.py` e ingresar a `http://127.0.0.1:8000`.
8. Crear el primer usuario desde la pantalla de registro.
