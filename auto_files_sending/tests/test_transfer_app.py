import tempfile
import threading
import unittest
from pathlib import Path

from transfer_app import TransferService, target_path, validate_folders


class TransferPathTests(unittest.TestCase):
    def test_target_path_keeps_source_subfolders(self):
        source = Path("C:/motec")
        file_path = source / "session-1" / "lap.ld"
        destination = Path("D:/shared")

        self.assertEqual(
            target_path(file_path, source, destination),
            destination / "session-1" / "lap.ld",
        )

    def test_validate_folders_rejects_destination_inside_source(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            source.mkdir()
            destination = source / "shared"

            with self.assertRaisesRegex(ValueError, "à l'intérieur"):
                validate_folders(source, destination)

    def test_validate_folders_creates_destination(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            destination = Path(temporary_directory) / "destination"
            source.mkdir()

            validated_source, validated_destination = validate_folders(source, destination)

            self.assertEqual(validated_source, source.resolve())
            self.assertEqual(validated_destination, destination.resolve())
            self.assertTrue(destination.is_dir())

    def test_service_copies_a_new_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            destination = Path(temporary_directory) / "destination"
            source.mkdir()
            copied = threading.Event()
            service = TransferService(
                lambda kind, message: copied.set() if kind == "copied" else None
            )

            service.start(source, destination)
            try:
                (source / "session.ld").write_bytes(b"telemetry")

                self.assertTrue(copied.wait(timeout=8), "Le fichier n'a pas été transféré.")
                self.assertEqual((destination / "session.ld").read_bytes(), b"telemetry")
            finally:
                service.stop()

    def test_service_renames_duplicate_without_overwriting_and_logs_it(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source"
            destination = Path(temporary_directory) / "destination"
            source.mkdir()
            destination.mkdir()
            original = destination / "session.ld"
            first_duplicate = destination / "session (1).ld"
            original.write_bytes(b"previous session")
            first_duplicate.write_bytes(b"another session")
            notifications = []
            copied = threading.Event()

            def notify(kind, message):
                notifications.append((kind, message))
                if kind == "copied":
                    copied.set()

            service = TransferService(notify)
            service.start(source, destination)
            try:
                (source / "session.ld").write_bytes(b"new session")

                self.assertTrue(copied.wait(timeout=8), "Le fichier n'a pas été transféré.")
                second_duplicate = destination / "session (2).ld"
                self.assertEqual(original.read_bytes(), b"previous session")
                self.assertEqual(first_duplicate.read_bytes(), b"another session")
                self.assertEqual(second_duplicate.read_bytes(), b"new session")
                self.assertIn(
                    (
                        "copied",
                        "Copié sous un nouveau nom : session.ld -> session (2).ld",
                    ),
                    notifications,
                )
            finally:
                service.stop()


if __name__ == "__main__":
    unittest.main()
