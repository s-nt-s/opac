#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Uso: bash publish.sh [--testpypi | --pypi] [--dry-run]

  --testpypi  Publica en TestPyPI (opción predeterminada).
  --pypi      Publica en PyPI; solicita confirmación explícita.
  --dry-run   Ejecuta pruebas, build y validación, pero no sube archivos.
  -h, --help  Muestra esta ayuda.

Puedes elegir otro intérprete con la variable PYTHON=/ruta/al/python.
EOF
}

REPOSITORY="testpypi"
DRY_RUN="false"
while (($#)); do
  case "$1" in
    --testpypi)
      REPOSITORY="testpypi"
      ;;
    --pypi)
      REPOSITORY="pypi"
      ;;
    --dry-run)
      DRY_RUN="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Opción desconocida: %s\n\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${PYTHON:-}" ]]; then
  PYTHON_BIN="$PYTHON"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No encuentro Python 3. Define PYTHON o crea .venv." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import build, twine' >/dev/null 2>&1; then
  echo "Instalando herramientas de construcción (build y twine)..."
  "$PYTHON_BIN" -m pip install --upgrade build twine
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
DIST_DIR="$WORK_DIR/dist"
mkdir -p "$DIST_DIR"

cd "$ROOT_DIR"
echo "Ejecutando pruebas..."
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
  "$PYTHON_BIN" -m unittest discover -s tests -v

echo "Construyendo wheel y sdist..."
"$PYTHON_BIN" -m build --outdir "$DIST_DIR"

shopt -s nullglob
ARTIFACTS=("$DIST_DIR"/*)
if ((${#ARTIFACTS[@]} == 0)); then
  echo "El build no generó artefactos." >&2
  exit 1
fi

echo "Validando artefactos..."
"$PYTHON_BIN" -m twine check "${ARTIFACTS[@]}"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "Simulación: no se ha subido nada. Artefactos generados:"
  printf '  %s\n' "${ARTIFACTS[@]}"
  exit 0
fi

if [[ "$REPOSITORY" == "pypi" ]]; then
  echo "ATENCIÓN: se publicará una versión en PyPI, visible para todo el mundo."
  read -r -p 'Escribe PUBLICAR para continuar: ' confirmation
  if [[ "$confirmation" != "PUBLICAR" ]]; then
    echo "Publicación cancelada."
    exit 1
  fi
fi

echo "Subiendo a ${REPOSITORY}..."
if [[ "$REPOSITORY" == "testpypi" ]]; then
  "$PYTHON_BIN" -m twine upload --repository testpypi "${ARTIFACTS[@]}"
else
  "$PYTHON_BIN" -m twine upload "${ARTIFACTS[@]}"
fi

echo "Publicación completada en ${REPOSITORY}."
