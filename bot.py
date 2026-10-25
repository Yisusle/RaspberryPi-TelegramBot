
async def close_vainilla_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await run_browser_command(
        update, "cerrar_vainilla", "Cerrando la pestaña de Vainilla."
    )


async def close_yisus_cmd(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await run_browser_command(
        update, "cerrar_yisus", "Cerrando la pestaña de Yisus."
    )


async def close_all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await run_browser_command(
        update, "cerrar_todo", "Cierre de pestañas solicitado."
    )


app.add_handler(CommandHandler("cerrar_vainilla", close_vainilla_cmd))
app.add_handler(CommandHandler("cerrar_yisus", close_yisus_cmd))
