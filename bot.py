
import os
import time
import asyncio
import logging
import json
import urllib.request
import urllib.error

from datetime import datetime

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

_raw_ids = os.getenv(
    "TELEGRAM_ALLOWED_USER_IDS",
    os.getenv("TELEGRAM_ALLOWED_USER_ID", ""),
)
ALLOWED_USER_IDS = {
    item.strip()
    for item in _raw_ids.split(",")
    if item.strip().isdigit()
}

LINK_1 = os.getenv("DIRECTO_1_URL", "").strip()
LINK_2 = os.getenv("DIRECTO_2_URL", "").strip()

BROWSER_CONTROL_URL = os.getenv(
    "BROWSER_CONTROL_URL",
    "http://host.docker.internal:8765/action",
).strip()

BROWSER_CONTROL_TOKEN = os.getenv(
    "BROWSER_CONTROL_TOKEN", ""
).strip()

started_at = time.monotonic()


def authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and str(user.id) in ALLOWED_USER_IDS)


async def guard(update: Update) -> bool:
    if authorized(update):
        return True

    if update.effective_message:
        await update.effective_message.reply_text("No autorizado.")

    return False


def format_uptime(seconds: float) -> str:
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def send_browser_action(action: str) -> dict:
    if not BROWSER_CONTROL_TOKEN:
        raise RuntimeError(
            "Falta configurar BROWSER_CONTROL_TOKEN en Portainer."
        )

    payload = json.dumps({"action": action}).encode("utf-8")

    request = urllib.request.Request(
        BROWSER_CONTROL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {BROWSER_CONTROL_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Controlador HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"No se pudo conectar con el controlador: {exc}"
        ) from exc

    if not result.get("ok", False):
        raise RuntimeError(result.get("error", "Error del controlador"))

    return result


async def browser_action(action: str) -> dict:
    return await asyncio.to_thread(send_browser_action, action)


async def run_browser_command(
    update: Update,
    action: str,
    success_message: str,
):
    if not await guard(update):
        return

    message = update.effective_message

    try:
        if action == "vainilla" and not LINK_1:
            await message.reply_text("Falta configurar DIRECTO_1_URL.")
            return

        if action == "yisus" and not LINK_2:
            await message.reply_text("Falta configurar DIRECTO_2_URL.")
            return

        if action == "ambos" and (not LINK_1 or not LINK_2):
            await message.reply_text(
                "Configura DIRECTO_1_URL y DIRECTO_2_URL en Portainer."
            )
            return

        result = await browser_action(action)

        if action == "recargar":
            count = result.get("reloaded", 0)
            errors = result.get("errors", [])

            reply = (
                f"Pestañas del bot recargadas: {count}."
                if count
                else "No hay pestañas del bot para recargar."
            )

            if errors:
                reply += f"\nAvisos: {len(errors)} pestaña(s) no se recargaron."

            await message.reply_text(reply)

        elif action in (
            "cerrar_todo",
            "cerrar_vainilla",
            "cerrar_yisus",
        ):
            count = result.get("closed", 0)
            await message.reply_text(
                f"{success_message}\nPestañas cerradas: {count}."
            )

        else:
            await message.reply_text(
                result.get("message", success_message)
            )

    except Exception as exc:
        log.exception("Error ejecutando la acción %s", action)
        await message.reply_text(f"No se pudo ejecutar el comando:\n{exc}")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    await update.effective_message.reply_text(
        "Control de Chromium en Raspberry Pi\n\n"
        "/estado — estado de la Raspberry Pi y pestañas\n"
        "/vainilla — abrir Vainilla\n"
        "/yisus — abrir Yisus\n"
        "/ambos — abrir ambos canales\n"
        "/recargar — recargar las pestañas del bot\n"
        "/cerrar_vainilla — cerrar solo Vainilla\n"
        "/cerrar_yisus — cerrar solo Yisus\n"
        "/cerrar_todo — cerrar las pestañas del bot\n"
        "/ayuda — mostrar esta ayuda"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update):
        return

    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    cpu = psutil.cpu_percent(interval=0.4)
    uptime = format_uptime(time.monotonic() - started_at)
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    lines = [
        "Estado de la Raspberry Pi",
        f"Hora local: {now}",
        f"Bot activo: {uptime}",
        f"CPU: {cpu:.0f}%",
        (
            f"RAM: {memory.percent:.0f}% usada "
            f"({memory.used / 1024**3:.1f}/"
            f"{memory.total / 1024**3:.1f} GiB)"
        ),
        (
            f"Disco raíz: {disk.percent:.0f}% usado "
            f"({disk.free / 1024**3:.1f} GiB libres)"
        ),
    ]

    # Consulta las pestañas reales si el controlador implementa /estado.
    try:
        result = await browser_action("estado")
        tabs = result.get("tabs", [])
        lines.append("")
        lines.append(f"Pestañas abiertas en Chromium: {len(tabs)}")

        for tab in tabs:
            title = tab.get("title") or "(sin título)"
            url = tab.get("url", "")
            channel = tab.get("channel", "")
            owned = tab.get("owned", False)

            if owned:
                label = {
                    "vainilla": "Vainilla",
                    "yisus": "Yisus",
                }.get(channel, "Bot")
                lines.append(f"• [{label}] {title}\n  {url}")
            else:
                lines.append(f"• [Personal] {title}\n  {url}")

    except Exception as exc:
        log.warning("No se pudo consultar las pestañas: %s", exc)
        lines.append("")
        lines.append("No se pudo consultar el listado de pestañas.")

    await update.effective_message.reply_text("\n".join(lines))


async def link1_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_browser_command(
        update, "vainilla", "Canal Vainilla abierto."
    )


async def link2_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_browser_command(
        update, "yisus", "Canal Yisus abierto."
    )


async def both_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_browser_command(
        update, "ambos", "Ambos canales abiertos."
    )


async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_browser_command(
        update, "recargar", "Recarga terminada."
    )


async def close_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_browser_command(
        update, "cerrar_todo", "Cierre de pestañas del bot."
    )


async def close_vainilla_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await run_browser_command(
        update, "cerrar_vainilla", "Cierre de Vainilla."
    )


async def close_yisus_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await run_browser_command(
        update, "cerrar_yisus", "Cierre de Yisus."
    )


async def post_init(application: Application):
    log.info("Bot iniciado.")
    log.info("IDs autorizados configurados: %d", len(ALLOWED_USER_IDS))


def main():
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN.")

    if not ALLOWED_USER_IDS:
        raise SystemExit(
            "Configura TELEGRAM_ALLOWED_USER_IDS con uno o varios "
            "IDs numéricos separados por comas."
        )

    app = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("ayuda", help_cmd))
    app.add_handler(CommandHandler("estado", status_cmd))
    app.add_handler(CommandHandler("vainilla", link1_cmd))
    app.add_handler(CommandHandler("yisus", link2_cmd))
    app.add_handler(CommandHandler("ambos", both_cmd))
    app.add_handler(CommandHandler("recargar", reload_cmd))
    app.add_handler(CommandHandler("cerrar_todo", close_all_cmd))
    app.add_handler(CommandHandler("cerrar_vainilla", close_vainilla_cmd))
    app.add_handler(CommandHandler("cerrar_yisus", close_yisus_cmd))

    log.info("Iniciando polling de Telegram.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
