import os
import time
import asyncio
import logging
from datetime import datetime, timezone

import aiohttp
import psutil
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("pi-monitor")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").strip()
LINK_1 = os.getenv("DIRECTO_1_URL", "").strip()
LINK_2 = os.getenv("DIRECTO_2_URL", "").strip()
CHECK_TIMEOUT = float(os.getenv("URL_CHECK_TIMEOUT", "8"))
started_at = time.monotonic()
monitor_tasks = set()


def authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and ALLOWED_USER_ID and str(user.id) == ALLOWED_USER_ID)


async def reject(update: Update):
    if update.effective_message:
        await update.effective_message.reply_text(
            "No autorizado. Configura tu TELEGRAM_ALLOWED_USER_ID en el archivo .env."
        )


async def guard(update: Update) -> bool:
    if not authorized(update):
        await reject(update)
        return False
    return True


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


async def check_url(url: str) -> str:
    if not url:
        return "No configurado"
    timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT)
    headers = {"User-Agent": "PiTelegramMonitor/1.0"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            # GET with a small response read is more compatible than HEAD for many sites.
            async with session.get(url, allow_redirects=True) as response:
                return f"HTTP {response.status} — enlace accesible"
    except asyncio.TimeoutError:
        return "Tiempo de espera agotado"
    except aiohttp.ClientError as exc:
        return f"No se pudo comprobar ({type(exc).__name__})"


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.effective_message.reply_text(
        "Bot de supervisión de la Raspberry Pi listo.\n\n"
        "/estado — estado de la Pi y enlaces\n"
        "/vainilla — recibir el enlace 1\n"
        "/yisus — recibir el enlace 2\n"
        "/ambos — recibir ambos enlaces\n"
        "/recargar — volver a comprobar los enlaces\n"
        "/cerrar_todo — cancelar tareas de supervisión activas\n"
        "/ayuda — mostrar comandos\n\n"
        "Este bot comprueba enlaces y recursos; no abre ni recarga reproductores."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.4)
    uptime = format_uptime(time.monotonic() - started_at)
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    text = (
        f"Estado del bot / Raspberry Pi\n"
        f"Hora local: {now}\n"
        f"Bot activo: {uptime}\n"
        f"CPU: {cpu:.0f}%\n"
        f"RAM: {mem.percent:.0f}% usada ({mem.used / 1024**3:.1f}/{mem.total / 1024**3:.1f} GiB)\n"
        f"Disco raíz: {disk.percent:.0f}% usado ({disk.free / 1024**3:.1f} GiB libres)\n\n"
        f"Enlace 1: {'configurado' if LINK_1 else 'no configurado'}\n"
        f"Enlace 2: {'configurado' if LINK_2 else 'no configurado'}"
    )
    await update.effective_message.reply_text(text)


async def send_link(update: Update, url: str, label: str):
    if not await guard(update):
        return
    if not url:
        await update.effective_message.reply_text(
            f"{label}: falta configurar la URL en el archivo .env."
        )
        return
    await update.effective_message.reply_text(f"{label}\n{url}")


async def link1_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_link(update, LINK_1, "Enlace 1")


async def link2_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_link(update, LINK_2, "Enlace 2")


async def both_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    lines = []
    lines.append(f"Enlace 1: {LINK_1 or 'no configurado'}")
    lines.append(f"Enlace 2: {LINK_2 or 'no configurado'}")
    await update.effective_message.reply_text("\n\n".join(lines), disable_web_page_preview=True)


async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    await update.effective_message.reply_text("Comprobando accesibilidad de los enlaces…")
    one, two = await asyncio.gather(check_url(LINK_1), check_url(LINK_2))
    await update.effective_message.reply_text(
        f"Comprobación de enlaces (no confirma si hay un directo activo):\n"
        f"1. {one}\n"
        f"2. {two}"
    )


async def close_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return
    current = asyncio.current_task()
    cancelled = 0
    for task in list(monitor_tasks):
        if task is not current and not task.done():
            task.cancel()
            cancelled += 1
    monitor_tasks.clear()
    await update.effective_message.reply_text(
        f"Supervisión detenida. Tareas canceladas: {cancelled}.\n"
        "No se cerraron pestañas del navegador ni procesos del sistema."
    )


async def post_init(application: Application):
    log.info("Bot started. Authorized Telegram user ID: %s", ALLOWED_USER_ID or "(missing)")


def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env")
    if not ALLOWED_USER_ID.isdigit():
        raise SystemExit("Configura TELEGRAM_ALLOWED_USER_ID con tu ID numérico de Telegram.")
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ayuda", help_cmd))
    app.add_handler(CommandHandler("estado", status_cmd))
    app.add_handler(CommandHandler("vainilla", link1_cmd))
    app.add_handler(CommandHandler("yisus", link2_cmd))
    app.add_handler(CommandHandler("ambos", both_cmd))
    app.add_handler(CommandHandler("recargar", reload_cmd))
    app.add_handler(CommandHandler("cerrar_todo", close_all_cmd))
    log.info("Polling started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
