import os
import datetime
import json
import PyPDF2
import pytesseract
from PIL import Image
from shiny import reactive
from utils.config_functions import load_raw_config, resolve_path

paths_config = load_raw_config(config_filename = "paths.yaml")

data_base_folder_path = resolve_path(paths_config['data_base_folder_path'])
tesseract_exe_path    = paths_config['tesseract_exe_path']

session_data = {
    "authenticated"      : reactive.Value(True),
    "username"           : reactive.Value("usuario_demo"),
    "chat_history"       : reactive.Value([]),
    "pdf_text"           : reactive.Value(""),
    "saved_chats"        : reactive.Value([]),
    "selected_chat"      : reactive.Value(None),
    "file_input_version" : reactive.Value(0)
    }

def get_user_dir():
    
    user_dir = os.path.join(data_base_folder_path, session_data["username"].get())
    
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    
    return user_dir

def list_saved_chats():
    
    user_dir = get_user_dir()
    
    if not os.path.exists(user_dir):
        return []
    
    return sorted([f for f in os.listdir(user_dir) if f.endswith(".json")], reverse = True)

def load_chat_by_name(chat_id):
    
    filename = f"{chat_id}.json"
    filepath = os.path.join(get_user_dir(), filename)
    
    if os.path.exists(filepath):
        with open(filepath, "r", encoding = "utf-8") as f:
            history = json.load(f)
        
        session_data["chat_history"].set(history)

def save_current_chat():
    
    username = session_data["username"].get()
    
    chat     = session_data["chat_history"].get()
    selected = session_data["selected_chat"].get()

    if selected is None:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{timestamp}.json"
        session_data["selected_chat"].set(timestamp)
    
    else:
        filename = f"{selected}.json"

    filepath = os.path.join(get_user_dir(), filename)
    
    with open(filepath, "w", encoding = "utf-8") as f:
        json.dump(chat, f, ensure_ascii = False, indent = 2)

    session_data["saved_chats"].set(list_saved_chats())

def extract_text_from_image(image_path: str) -> str:
    
    try:
        img = Image.open(image_path)
        pytesseract.pytesseract.tesseract_cmd = tesseract_exe_path
        ocr_text = pytesseract.image_to_string(img)
        
        return ocr_text.strip()
    
    except Exception as e:
        print(f"Error al procesar la imagen {image_path}: {e}")
        
        return ""

def extract_text_from_pdf(path):
    
    reader = PyPDF2.PdfReader(path)
    text   = ""

    for page in reader.pages:
        text += page.extract_text()

    return text.strip()
