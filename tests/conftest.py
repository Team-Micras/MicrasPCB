import shutil

import pytest

needs_kicad = pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="kicad-cli not installed")
