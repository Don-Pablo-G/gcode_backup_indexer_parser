"""Light GUI smoke: construct widgets without mainloop when a display is available."""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    not os.environ.get("DISPLAY") and os.name != "nt",
    reason="No DISPLAY for Tk on this Linux host",
)
def test_indexer_app_constructs():
    from tests.tk_util import require_working_tk

    require_working_tk()
    from gcode_index.gui import IndexerApp

    app = IndexerApp()
    try:
        assert app.title()
        app.update_idletasks()
    finally:
        app.destroy()
