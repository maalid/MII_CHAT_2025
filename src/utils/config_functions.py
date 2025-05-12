import yaml
from pathlib import Path

def load_raw_config(config_filename) -> dict:
    """
    Carga el YAML desde config/ sin modificar los valores.
    Retorna un diccionario con strings y estructuras anidadas.
    """
    app_root = Path(__file__).parent.parent.resolve()
    config_path = app_root / "config" / config_filename

    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def resolve_path(path_str: str, base_dir: Path = None) -> Path:
    """
    Convierte un string a Path absoluto solo si es relativo.
    Por defecto, usa la raíz del proyecto como base.
    """
    path_obj = Path(path_str)

    if path_obj.is_absolute():
        return path_obj
    else:
        if base_dir is None:
            base_dir = Path(__file__).parent.resolve()
        return (base_dir / path_obj).resolve()
