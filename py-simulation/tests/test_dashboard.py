"""Dashboard smoke tests via streamlit.testing.v1.AppTest.

Covers: app boots, presets mutate widget state safely, and the
Educational → Simulation geometry handoff produces matching widget values.
"""

import unittest

from streamlit.testing.v1 import AppTest

APP = "src/dashboard/app.py"
TIMEOUT = 180


def _boot() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.run()
    return at


class TestDashboard(unittest.TestCase):
    def test_app_boots_without_exceptions(self):
        at = _boot()
        self.assertEqual([str(e.value) for e in at.exception], [])

    def test_quick_preset_updates_widget_state(self):
        at = _boot()
        at.button(key="preset_quick").click().run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        self.assertEqual(at.slider(key="signal.duration").value, 4.0)
        self.assertEqual(at.slider(key="srpphat.search.resolution_deg").value, 4.0)

    def test_default_preset_resets_after_quick(self):
        at = _boot()
        at.button(key="preset_quick").click().run()
        at.button(key="preset_default").click().run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        self.assertEqual(at.slider(key="signal.duration").value, 5.0)

    def test_geometry_handoff_from_educational_tab(self):
        at = _boot()
        at.slider(key="edu_r1").set_value(0.5)
        at.slider(key="edu_n1").set_value(12)
        at.run()
        at.button(key="edu_send_geom").click().run()
        self.assertEqual([str(e.value) for e in at.exception], [])
        self.assertEqual(at.slider(key="array.dual_ring.ring1_radius").value, 0.5)
        self.assertEqual(at.slider(key="array.dual_ring.n_mics_ring1").value, 12)

    def test_form_produces_valid_config_via_free_text_parsing(self):
        from src.dashboard.forms import _parse_free_text
        self.assertIsNone(_parse_free_text(""))
        self.assertIsNone(_parse_free_text("None"))
        self.assertEqual(_parse_free_text("30"), 30)
        self.assertEqual(_parse_free_text("[1, 2]"), [1, 2])
        self.assertEqual(
            _parse_free_text('{"azimuth_deg": 5.0, "elevation_deg": 10.0}'),
            {"azimuth_deg": 5.0, "elevation_deg": 10.0},
        )
        self.assertEqual(_parse_free_text("phat"), "phat")
