# FPGA_Visualizer

This repository contains a Python-based visualization tool for FPGA designs.

## Requirements

- Python 3.8+
- A virtual environment tool (venv, virtualenv, or similar)
- The Python dependencies listed in requirements.txt

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/CelIsDividing/FPGA_Visualizer.git
   cd FPGA_Visualizer
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv venv
   source venv/bin/activate   # macOS / Linux
   venv\Scripts\activate    # Windows (PowerShell/Command Prompt)
   ```

3. Install dependencies:

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Running the program

The main entry point is `main.py`. Run it with:

```bash
python main.py
```

By default the application runs as a local web service (Flask or similar) on http://127.0.0.1:5000. If the app prints a different host/port in the console, use that address.

If you need to run in development mode and reload on changes, run with the FLASK environment variables (if the project uses Flask):

```bash
export FLASK_APP=main.py
export FLASK_ENV=development
flask run
```

(on Windows PowerShell use `setx` or `$env:FLASK_APP = "main.py"` to set environment variables)

## Uploading and input files

- The repository contains directories such as `uploads/`, `parsers/` and `visualization/`. Use the web UI to upload files if provided.
- If the program expects a specific input file format, place those files into the `uploads/` or `input/` directory as described in the web UI or code comments.

## Configuration

- Check the `config/` directory for configuration files; adjust paths or settings there as needed.
- If the application relies on environment variables, set them before running.

## Troubleshooting

- If a dependency install fails, double-check your Python version and that your virtual environment is active.
- If `main.py` fails with an ImportError, ensure `pip install -r requirements.txt` completed successfully.
- Check the console output for stack traces; the repo contains `logs/` or `output/` directories that may help.

## Development notes

- Source code entry points and parsing logic are in `main.py`, `parsers/`, and `visualization/`.
- Static assets and templates are under `static/` and `templates/`.

## License

Refer to the repository for license information (LICENSE file) or contact the repository owner.
