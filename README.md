# Bot de Telegram para supervisar la Raspberry Pi

Este proyecto incluye comandos para recibir enlaces, revisar si responden por HTTP y consultar métricas básicas del proceso/contenedor. **No abre, reproduce ni recarga automáticamente reproductores de directos**, y la comprobación HTTP no demuestra que un directo esté activo ni genera visualizaciones.

## 1. Preparar el proyecto

En la Raspberry Pi, crea una carpeta y copia estos archivos. Si descargaste el ZIP:

```bash
mkdir -p ~/pi-telegram-monitor
cd ~/pi-telegram-monitor
unzip pi_telegram_monitor.zip
```

Si el ZIP se descomprime dentro de una carpeta, entra a esa carpeta antes de seguir.

## 2. Configurar credenciales

```bash
cp .env.example .env
nano .env
```

Rellena:
- `TELEGRAM_BOT_TOKEN`: token que ya tienes de BotFather.
- `TELEGRAM_ALLOWED_USER_ID`: tu ID numérico de Telegram (no es el @usuario).
- `DIRECTO_1_URL` y `DIRECTO_2_URL`: los dos enlaces que quieres tener a mano.

No compartas el `.env` ni subas el token a Git.

## 3. Ejecutar con Docker Compose

Necesitas Docker y el complemento `docker compose` instalado:

```bash
docker compose up -d --build
docker compose logs -f
```

Para reiniciar después de editar `.env`:

```bash
docker compose up -d --build
```

Para detener:

```bash
docker compose down
```

## 4. Comandos disponibles

- `/start` o `/ayuda`: instrucciones.
- `/estado`: CPU, RAM, disco y tiempo activo del bot.
- `/directo1`: envía el primer enlace.
- `/directo2`: envía el segundo enlace.
- `/ambos`: envía ambos enlaces.
- `/recargar`: vuelve a comprobar que las URLs respondan por HTTP. No confirma que haya transmisión en vivo.
- `/cerrar_todo`: cancela tareas de supervisión creadas por el bot; no cierra pestañas ni mata procesos del sistema.

## 5. Sin Docker (alternativa)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python bot.py
```

Para producción, es preferible ejecutarlo como contenedor con reinicio automático.

## Seguridad

El bot solo responde al ID numérico configurado en `TELEGRAM_ALLOWED_USER_ID`. Si no se configura correctamente, no arranca. Mantén el token privado y regénéralo con BotFather si se expone.
