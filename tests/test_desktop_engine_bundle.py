import io
from pathlib import Path
import subprocess
import tarfile
from unittest import TestCase
from unittest.mock import patch

import test_myarch as fixtures
from myarch import common, engine, plan, snapshot


class DesktopEngineBundle(TestCase):
    setUp = fixtures.Isolated.setUp
    tearDown = fixtures.Isolated.tearDown
    make_capture = fixtures.Isolated.make_capture

    def engine_source(self):
        source = self.root / 'desktop engine'
        for relative, data, mode in [
            ('desktop-manager', '#!/bin/sh\necho manager\n', 0o755),
            ('desktopctl', '#!/bin/sh\necho catalog\n', 0o755),
            ('desktop_engine/cli.py', '# Engine fixture\n', 0o644),
            ('ui/shell.qml', 'import QtQuick\n', 0o644),
            ('collection/themes/demo.json', '{}\n', 0o644),
            ('integration/demo.patch', '# Patch fixture\n', 0o644),
            ('desktop_engine/__pycache__/old.pyc', 'cache', 0o644),
        ]:
            common.atomic_bytes(source / relative, data.encode(), mode=mode)
        return source

    def captured_with_engine(self):
        self.make_capture()
        source = self.engine_source()
        result = snapshot.capture(desktop_engine_source=source)
        return snapshot.load_snapshot(result['id'])

    def test_bundle_roundtrip_preserves_runnable_project(self):
        capture = self.captured_with_engine()
        common.atomic_json(self.root/'manifests/packages.json', {'packages': []})
        plan.source_guard()
        backup = engine.backup_bundle(capture['id'])
        self.assertTrue(engine.check_bundle(Path(backup['bundle']))['valid'])
        result = engine.stage(capture['id'])
        restored = Path(result['desktop_engine'])
        self.assertEqual((restored / 'collection/themes/demo.json').read_text(), '{}\n')
        self.assertFalse((restored / 'desktop_engine/__pycache__').exists())
        proc = subprocess.run([str(restored/'desktopctl')], capture_output=True, text=True, check=True)
        self.assertEqual(proc.stdout.strip(), 'catalog')

    def test_later_capture_keeps_the_engine(self):
        original = self.captured_with_engine()
        with patch.object(snapshot, 'now', return_value='2030-01-01T00:00:00+00:00'):
            later = snapshot.load_snapshot(snapshot.capture()['id'])
        self.assertEqual(later['resources'], original['resources'])

    def test_installer_places_launcher_for_destination(self):
        captured = self.captured_with_engine()
        with patch.object(engine, 'require_destination_host'):
            result = engine.install_desktop_engine(captured['id'])
        launcher = Path(result['launcher'])
        self.assertEqual(launcher.name, 'desktop-engine-manager.desktop')
        self.assertIn('Exec=/bin/sh -c "exec ~/.local/share/myarch/desktop-engine/', launcher.read_text())
        self.assertTrue((Path(result['desktop_engine'])/'desktop-manager').stat().st_mode & 0o100)
        launcher.write_text('local customization\n')
        with patch.object(engine, 'require_destination_host'):
            with self.assertRaisesRegex(ValueError, 'existing launcher'):
                engine.install_desktop_engine(captured['id'])
        self.assertEqual(launcher.read_text(), 'local customization\n')

    def test_install_restores_profiles_once_and_preserves_destination_profiles(self):
        source_profiles = self.home/'.local/state/desktop-engine/profiles.json'
        profile = {'custom': {'id': 'custom', 'name': 'My desktop'}}
        common.atomic_json(source_profiles, profile)
        captured = self.captured_with_engine()
        source_profiles.unlink()  # A fresh destination starts with no profile data.

        with patch.object(engine, 'require_destination_host'):
            result = engine.install_desktop_engine(captured['id'])
            self.assertEqual(result['profiles_status'], 'restored')
            self.assertEqual(common.read_json(source_profiles), profile)

            local_profile = {'other': {'id': 'other', 'name': 'Destination profile'}}
            common.atomic_json(source_profiles, local_profile)
            result = engine.install_desktop_engine(captured['id'])
            self.assertEqual(result['profiles_status'], 'existing_preserved')
            self.assertEqual(common.read_json(source_profiles), local_profile)

    def test_archive_validation_rejects_paths_outside_project(self):
        from myarch import desktop_engine
        archive = self.root / 'unsafe.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            entry = tarfile.TarInfo('../escaped')
            entry.size = 1
            tar.addfile(entry, io.BytesIO(b'x'))
        with self.assertRaises(ValueError):
            desktop_engine.extract_project(archive, self.root/'stage')
        self.assertFalse((self.root/'escaped').exists())
