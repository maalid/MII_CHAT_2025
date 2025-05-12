import os
import openai
import asyncio
from dotenv import load_dotenv
from pathlib import Path
from shiny import App, ui, reactive, render, req
from utils.config_functions import load_raw_config, resolve_path
from utils.utils_functions import (
    session_data,
    get_user_dir,
    list_saved_chats,
    load_chat_by_name,
    save_current_chat,
    extract_text_from_pdf,
    extract_text_from_image
)


paths_config = load_raw_config(config_filename = "paths.yaml")

static_folder_path = resolve_path(paths_config['statics']['folder_path'])
styles_file_path   = resolve_path(paths_config["styles_file_path"])
logo_file_name     = paths_config["statics"]["logo_file_name"]


load_dotenv()
llm_model_config = load_raw_config(config_filename = "llm.yaml")

llm_model_name = llm_model_config['default_llm']['model_name']
client = openai.OpenAI(api_key = os.getenv("OPENAI_API_KEY"))

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.tags.h2("Mis Chats", class_="sidebar-title"),
        ui.input_action_button(id="new_chat", label="➕ Nuevo Chat", lass_="button-new"),
        ui.output_ui(id="saved_chats_ui")
    ),
    ui.include_css(path=css_file_path),
    ui.div(ui.img(src=f"/{logo_file_name}", height="90px"), style="margin-bottom: 0.5rem;"),
    ui.div(
        ui.output_ui("chat_area"),
        ui.div(
            ui.input_text_area(
                id="user_input", label="", rows=2,
                placeholder="Pregunta lo que quieras", width="100%"
            ),
            ui.input_action_button(id="send", label="Enviar", class_="send-button"),
            ui.div(
                {"style": "width: 30%; height: 99px;"},
                ui.output_ui("dynamic_file_input")
            ),
            class_="input-container"
        ),
        class_="main-content"
    ),
    ui.tags.script("""
        document.getElementById("user_input").addEventListener("input", function () {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
    """),
    ui.tags.script("""
        function scrollChatToBottom() {
            const el = document.getElementById("chat-box");
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        }
    
        Shiny.addCustomMessageHandler("scroll_to_bottom", function(msg) {
            setTimeout(scrollChatToBottom, 100);  // pequeño delay tras actualización UI
        });
    
        // Backup: scroll automático cuando se agregan nodos
        const observer = new MutationObserver(scrollChatToBottom);
        const interval = setInterval(() => {
            const chatBox = document.getElementById("chat-box");
            if (chatBox) {
                observer.observe(chatBox, { childList: true, subtree: true });
                clearInterval(interval);
            }
        }, 200);
    """)
)

def server(input, output, session):

    @output
    @render.ui
    def dynamic_file_input():
        return ui.input_file(
            id           = f"file_input_{session_data['file_input_version'].get()}",
            label        = " ",
            multiple     = False,
            accept       = ["application/pdf", "image/png", "image/jpeg"],
            button_label = "archivos",
            placeholder  = "..."
        )

    @output
    @render.ui
    def saved_chats_ui():
        _ = session_data["saved_chats"].get()
        if not session_data["authenticated"].get():
            return ui.p("Inicia sesión para ver tus chats.")
        chats = list_saved_chats()
        selected_chat = session_data["selected_chat"].get()
        return ui.tags.ul(
            *[
                ui.tags.li(
                    ui.div(
                        ui.input_action_link(
                            id=f"chat_{chat_id}",
                            label=f"📂 {chat_id}",
                            class_="chat-link" + (" selected-chat" if selected_chat == chat_id else "")
                        ),
                        ui.tags.div(
                            ui.input_text(id=f"rename_input_{chat_id}", label="", placeholder="Nuevo nombre"),
                            ui.input_action_button(id=f"rename_{chat_id}", label="✏️ Renombrar", class_="chat-action"),
                            ui.input_action_button(id=f"delete_{chat_id}", label="🗑 Eliminar", class_="chat-action"),
                            class_="dropdown-menu"
                        ),
                        class_="chat-entry"
                    )
                )
                for chat in chats
                for chat_id in [chat[:-5]]
            ],
            class_="chat-list"
        )

    @output
    @render.ui
    def chat_area():
        if not session_data["authenticated"].get():
            return ui.p("Inicia sesión para empezar a chatear.")
        history = session_data["chat_history"].get()
        items = []
        for msg in history:
            if msg["role"] == "system":
                continue
            class_name = "user-msg" if msg["role"] == "user" else "assistant-msg"
            items.append(ui.div(ui.markdown(msg["content"]), class_=f"chat-bubble {class_name}"))
        return ui.div(*items,
              class_ = "chat-container chat-box",
              id     = "chat-box")
    @reactive.effect
    @reactive.event(input.send)
    async def handle_input():
        if not session_data["authenticated"].get():
            return
    
        msg = input.user_input().strip()
        if not msg:
            return
    
        history = list(session_data["chat_history"].get())
        history.append({"role": "user", "content": msg})
    
        context = session_data["pdf_text"].get()
        if context:
            history.append({
                "role": "system",
                "content": f"Contexto del documento:\n{context[:50000]}"
            })
    
        response = client.chat.completions.create(
            model=llm_model_name,
            messages=history[-10:]
        )
    
        reply = response.choices[0].message.content.strip()
    
        history.append({
            "role": "assistant",
            "content": reply,
            "animated": True
        })
    
        session_data["chat_history"].set(history)
    
        save_current_chat()
        ui.update_text(id="user_input", value="")
    
        await session.send_custom_message("scroll_to_bottom", {})
        await session.send_custom_message("animate_assistant_reply", {
            "text": reply,
            "id": "assistant_msg"
        })

    @reactive.effect
    @reactive.event(input.new_chat)
    def start_new_chat():
        current = session_data["chat_history"].get()
        if current:
            save_current_chat()
    
        # Eliminar archivo anterior cargado si existe
        file_input_id = f"file_input_{session_data['file_input_version'].get()}"
        file_info = getattr(input, file_input_id)()
        if file_info:
            uploaded_path = file_info[0]["datapath"]
            try:
                os.remove(uploaded_path)
            except Exception as e:
                print(f"⚠️ No se pudo eliminar el archivo cargado: {e}")
    
        # Reset de estados
        session_data["chat_history"].set([])
        session_data["pdf_text"].set("")
        session_data["selected_chat"].set(None)
        session_data["saved_chats"].set(list_saved_chats())
        ui.update_text(id="user_input", value="")
        session_data['file_input_version'].set(session_data['file_input_version'].get() + 1)
    
        # Refrescar la app forzando recarga con JS
        ui.tags.script("window.location.reload();")

    @reactive.effect
    def handle_file():
        if not session_data["authenticated"].get():
            return
        file_input_id = f"file_input_{session_data['file_input_version'].get()}"
        file_info = getattr(input, file_input_id)()
        if file_info:
            filepath = file_info[0]["datapath"]
            mimetype = file_info[0]["type"]
            if mimetype == "application/pdf":
                with open(filepath, "rb") as f:
                    text = extract_text_from_pdf(f)
            elif mimetype in ["image/png", "image/jpeg"]:
                text = extract_text_from_image(filepath)
            else:
                text = "Formato no soportado"
            session_data["pdf_text"].set(text)
            print(f"Texto extraído del archivo: {text[:500]}...")

    @reactive.effect
    def handle_chat_selection():
        for chat in list_saved_chats():
            chat_id = chat[:-5]
            btn_id = f"chat_{chat_id}"
    
            if getattr(input, btn_id)():
                # Eliminar archivo anterior si existe
                file_input_id = f"file_input_{session_data['file_input_version'].get()}"
                file_info = getattr(input, file_input_id)()
                if file_info:
                    uploaded_path = file_info[0]["datapath"]
                    try:
                        os.remove(uploaded_path)
                        print(f"🗑 Archivo eliminado: {uploaded_path}")
                    except Exception as e:
                        print(f"⚠️ No se pudo eliminar el archivo: {e}")
    
                # Resetear el input_file
                session_data['file_input_version'].set(session_data['file_input_version'].get() + 1)
    
                # Limpiar contexto anterior
                session_data["pdf_text"].set("")
    
                # Cargar el historial del chat seleccionado
                session_data["selected_chat"].set(chat_id)
                load_chat_by_name(chat_id)

    @reactive.effect
    def handle_chat_deletion():
        for chat in list_saved_chats():
            chat_id = chat[:-5]
            btn_id = f"delete_{chat_id}"
            if getattr(input, btn_id)():
                filepath = os.path.join(get_user_dir(), chat)
                if os.path.exists(filepath):
                    os.remove(filepath)
                if session_data["selected_chat"].get() == chat_id:
                    session_data["chat_history"].set([])
                    session_data["selected_chat"].set(None)
                session_data["saved_chats"].set(list_saved_chats())

    @reactive.effect
    def handle_chat_rename():
        for chat in list_saved_chats():
            chat_id = chat[:-5]
            btn_id = f"rename_{chat_id}"
            if getattr(input, btn_id)():
                rename_input = getattr(input, f"rename_input_{chat_id}")()
                if rename_input:
                    new_name = rename_input.strip()
                    if not new_name:
                        continue
                    old_path = os.path.join(get_user_dir(), f"{chat_id}.json")
                    new_path = os.path.join(get_user_dir(), f"{new_name}.json")
                    if os.path.exists(new_path):
                        continue
                    os.rename(old_path, new_path)
                    if session_data["selected_chat"].get() == chat_id:
                        session_data["selected_chat"].set(new_name)
                    session_data["saved_chats"].set(list_saved_chats())

app = App(app_ui, server, static_assets=str(static_folder_path))
