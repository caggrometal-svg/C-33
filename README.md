# C-33

C-33 es la base de una IA independiente diseñada alrededor de tres capacidades:

1. **Pensamiento:** un ciclo de razonamiento y decisión desacoplado del proveedor de IA.
2. **Internet:** una herramienta web aislada para búsquedas y acceso HTTP.
3. **Memoria:** una interfaz de persistencia de contexto preparada para evolucionar a un backend duradero.

## Estructura

```text
C-33/
├── src/
│   ├── core/
│   │   ├── config.py
│   │   └── logging.py
│   ├── agent/
│   │   └── brain.py
│   ├── tools/
│   │   └── web.py
│   ├── memory/
│   │   └── store.py
│   └── main.py
├── .env.example
├── .gitignore
└── pyproject.toml
```

## Requisitos

- Python 3.12 o 3.13
- pip

## Instalación

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

## Ejecución

```bash
uvicorn main:app --app-dir src --reload
```

Comprobar:

```bash
curl http://127.0.0.1:8000/health
```

La fundación no contiene proveedores propietarios ni workflows de GitHub Actions. Las futuras integraciones se conectarán mediante interfaces aisladas.
