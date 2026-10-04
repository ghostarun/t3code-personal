import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('switcher', Path(__file__).with_name('codex-switcher.py'))
switcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(switcher)


class SwitcherTests(unittest.TestCase):
    def test_existing_instance_is_reused_without_hiding_or_raising_it(self):
        with patch.object(switcher, 'running_pids', return_value=[42]), \
             patch.object(switcher, 'start_service') as start, \
             patch.object(switcher, 'request_window_hide') as hide:
            self.assertEqual(switcher.ensure_running(), ('already running', [42]))
            start.assert_not_called()
            hide.assert_not_called()

    def test_cold_start_hides_new_window_and_waits_for_background_state(self):
        clock = [0]

        def sleep(seconds):
            clock[0] += seconds

        with patch.object(switcher, 'running_pids', side_effect=[[], [42], [42], [42], [42]]), \
             patch.object(switcher, 'start_service') as start, \
             patch.object(switcher, 'request_window_hide') as hide, \
             patch.object(switcher, 'visible_windows', side_effect=[[1234], [], [], [], []]), \
             patch.object(switcher.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(switcher.time, 'sleep', side_effect=sleep):
            self.assertEqual(switcher.ensure_running(), ('started in background', [42]))
            start.assert_called_once()
            hide.assert_called_once_with(1234)

    def test_startup_failure_is_reported(self):
        with patch.object(switcher, 'running_pids', return_value=[]), \
             patch.object(switcher, 'start_service', side_effect=RuntimeError('missing launcher')):
            with self.assertRaisesRegex(RuntimeError, 'missing launcher'):
                switcher.ensure_running()


if __name__ == '__main__':
    unittest.main()
