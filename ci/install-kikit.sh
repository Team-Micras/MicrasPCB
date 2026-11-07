#!/usr/bin/env bash
# KiKit (versions.env KIKIT_VERSION), which builds the wall board's assembly panel (`make fab`),
# in a virtual environment on KiCad's own Python: KiKit drives KiCad's pcbnew module, which only
# that interpreter can load. Needs KiCad (ci/install-kicad.sh) and uv. Fails unless the installed
# kikit reports the pinned version.
set -euo pipefail
cd "$(dirname "$0")/.."
. ./versions.env

PY="${KICAD_PYTHON:-/usr/bin/python3}"
ENV="$HOME/.cache/micras-pcb/kikit-$KIKIT_VERSION"
"$PY" -c "import pcbnew" || { echo "error: $PY cannot import pcbnew: install KiCad (ci/install-kicad.sh) or set KICAD_PYTHON"; exit 1; }
uv venv -q --allow-existing --system-site-packages --python "$PY" "$ENV"
uv pip install -q --python "$ENV/bin/python" "kikit==$KIKIT_VERSION"

got="$("$ENV/bin/kikit" --version)"
if [ "$got" != "kikit, version $KIKIT_VERSION" ]; then
  echo "::error::$got installed, versions.env pins KiKit $KIKIT_VERSION"
  exit 1
fi
echo "$got in $ENV"
