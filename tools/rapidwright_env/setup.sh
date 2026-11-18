#!/usr/bin/env bash
# Install the pinned RapidWright (brief 100) into tools/rapidwright_env/venv. No root. Uses Vivado's own JRE (see flow/rapidwright_pin.py).
# The wheel's first import downloads rapidwright-<ver>-standalone-lin64.jar from AMD's GitHub release into the venv; device files are
# downloaded on first use. Both stay git-ignored. Hashes are checked against flow/rapidwright_pin.py.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PIN="$HERE/../../flow/rapidwright_pin.py"
VER=$(python3 -c "import runpy,sys; print(runpy.run_path('$PIN')['RAPIDWRIGHT_VERSION'])")
JP=$(python3 -c "import runpy,sys; print(runpy.run_path('$PIN')['JPYPE_VERSION'])")
python3 -m venv "$HERE/venv"
"$HERE/venv/bin/pip" install -q "jpype1==$JP" "rapidwright==$VER"
JAVA_HOME=$(python3 -c "import runpy; print(runpy.run_path('$PIN')['JAVA_HOME'])")
export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"
"$HERE/venv/bin/python" -I -c "import rapidwright; print('rapidwright', rapidwright.version)"
( cd "$HERE/venv/lib"/python3*/site-packages/rapidwright && sha256sum ./*.jar )
echo "compare the printed jar hash with JAR_SHA256 in flow/rapidwright_pin.py"
