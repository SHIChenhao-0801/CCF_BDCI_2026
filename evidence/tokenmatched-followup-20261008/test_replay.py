import hashlib,json,tempfile,unittest
from pathlib import Path
import socket
import replay
class PublicReplayTests(unittest.TestCase):
    def test_portable_recorded_windows_relative_path(self):
        root=Path('example')
        self.assertEqual(replay.PortableRecordedRoot(root)/'process\\run14-input\\dataset.json',root/'process/run14-input/dataset.json')
    def test_tampered_payload_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);payload=root/'payload';payload.write_bytes(b'original')
            manifest={'files':{'payload':hashlib.sha256(payload.read_bytes()).hexdigest()}}
            (root/'public-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            replay.verify_manifest(root);payload.write_bytes(b'tampered')
            with self.assertRaises(AssertionError):replay.verify_manifest(root)
    def test_manifest_cannot_read_outside_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'bundle';root.mkdir();outside=Path(temp)/'outside';outside.write_bytes(b'outside')
            (root/'public-manifest.json').write_text(json.dumps({'files':{'../outside':hashlib.sha256(outside.read_bytes()).hexdigest()}}),encoding='utf-8')
            with self.assertRaisesRegex(AssertionError,'leaves'):replay.verify_manifest(root)
    def test_socket_network_is_blocked(self):
        with self.assertRaisesRegex(RuntimeError,'forbidden'):socket.getaddrinfo('example.invalid',443)
    def test_actual_raw_replay_preserves_missing_and_unknown(self):
        result=replay.replay()
        self.assertEqual(result['phase_state_counts'],{'complete_primary_pair':271,'missing':1,'unattempted_or_interrupted':103})
        self.assertEqual(result['primary']['planned'],375)
        self.assertEqual(result['budget']['global_unknown_before'],13)
        self.assertEqual(result['budget']['global_unknown_after'],14)
        self.assertTrue(result['budget']['original_after_had_active_reservations'])
        self.assertEqual(result['model_api_calls'],0)
        self.assertEqual(result['network_requests'],0)
if __name__=='__main__':unittest.main()
