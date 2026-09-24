# C-33

Núcleo funcional de una IA independiente con tres capacidades coordinadas:

- **ReAct:** ciclo acotado de planificación, uso de memoria, búsqueda web y síntesis.
- **Internet:** búsqueda DuckDuckGo, descarga HTTP(S), extracción de texto limpio y resumen ligero.
- **Memoria:** persistencia local JSON con recuperación de contexto reciente y relevante.

## Estructura

\`\`\`text
C-33/
├── src/
│   ├── core/
│   │   └── config.py
│   ├── agent/
│   │   └── brain.py
│   ├── tools/
│   │   └── web.py
│   ├── memory/
│   │   └── store.py
│   └── main.py
├── .env.example
├── .gitignore
├── pyproject.toml
└── requirements.txt
\`\`\`

## Requisitos

Python 3.12 o 3.13.

## Instalación

\`\`\`bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
\`\`\`

## Activación de un modelo

C-33 no fija un proveedor propietario. Para habilitar planificación y síntesis con un endpoint compatible con Chat Completions, configura en \`.env\`:

\`\`\`text
MODEL_BASE_URL=https://tu-endpoint/v1
MODEL_NAME=tu-modelo
MODEL_API_KEY=tu-clave-opcional
\`\`\`

Sin estas variables, el núcleo sigue operativo en modo local: puede consultar memoria, acceder a la web y entregar el contexto recuperado de forma transparente.

## Ejecución interactiva

\`\`\`bash
python src/main.py
\`\`\`

Comandos de sesión:

- \`/clear\` limpia la memoria persistente.
- \`/memory\` muestra cuántas interacciones están guardadas.
- \`/exit\` termina la sesión.

La interfaz muestra únicamente acciones observables del ciclo ReAct; no expone razonamiento interno o cadena de pensamiento privada.
