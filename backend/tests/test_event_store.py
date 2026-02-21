"""
Tests for event_store.py: EventStore open, append, replay, clear, and malformed line handling.
"""

import json

import pytest
from event_store import EventStore


class TestEventStoreOpen:
    def test_open_creates_file(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)
        assert (tmp_path / "test_events.jsonl").exists()
        store.close()

    def test_open_new_file_seq_zero(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)
        assert store._seq == 0
        store.close()

    def test_open_resumes_sequence(self, tmp_path):
        """Opening a file with existing events should resume the sequence counter."""
        path = tmp_path / "test_events.jsonl"
        # Write 3 valid events manually
        with open(path, "w") as f:
            for i in range(1, 4):
                f.write(json.dumps({"seq": i, "type": "test", "payload": {}}) + "\n")

        store = EventStore()
        store.open(str(path))
        assert store._seq == 3
        store.close()

    def test_open_creates_parent_directories(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "subdir" / "deep" / "events.jsonl")
        store.open(path)
        assert (tmp_path / "subdir" / "deep" / "events.jsonl").exists()
        store.close()


class TestEventStoreAppend:
    def test_append_writes_json_line(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("draft_update", {"player": "Mahomes", "price": 30})

        store.close()

        with open(path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["seq"] == 1
        assert record["type"] == "draft_update"
        assert record["payload"]["player"] == "Mahomes"
        assert "ts" in record

    def test_append_increments_sequence(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("event1", {"data": 1})
        store.append("event2", {"data": 2})
        store.append("event3", {"data": 3})

        store.close()

        with open(path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["seq"] == 1
        assert json.loads(lines[1])["seq"] == 2
        assert json.loads(lines[2])["seq"] == 3

    def test_append_without_open_is_noop(self, tmp_path):
        """Appending without calling open() should silently do nothing."""
        store = EventStore()
        # Don't call open
        store.append("test", {"data": 1})  # Should not raise

    def test_append_after_resume(self, tmp_path):
        """Appending after reopening should continue the sequence."""
        path = tmp_path / "test_events.jsonl"

        # First session
        store1 = EventStore()
        store1.open(str(path))
        store1.append("event1", {"data": 1})
        store1.append("event2", {"data": 2})
        store1.close()

        # Reset singleton for second session
        EventStore._instance = None

        # Second session
        store2 = EventStore()
        store2.open(str(path))
        assert store2._seq == 2  # Resumed from 2
        store2.append("event3", {"data": 3})
        store2.close()

        with open(path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 3
        assert json.loads(lines[2])["seq"] == 3


class TestEventStoreReplay:
    def test_replay_returns_all_events(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("draft_update", {"player": "A"})
        store.append("draft_update", {"player": "B"})
        store.append("manual", {"player": "C"})

        events = store.replay()
        assert len(events) == 3
        store.close()

    def test_replay_sorted_by_seq(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("e1", {})
        store.append("e2", {})
        store.append("e3", {})

        events = store.replay()
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)
        store.close()

    def test_replay_empty_file(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        events = store.replay()
        assert events == []
        store.close()

    def test_replay_no_file(self, tmp_path):
        store = EventStore()
        # No file opened, no path exists
        events = store.replay()
        assert events == []

    def test_replay_skips_malformed_lines(self, tmp_path):
        """Malformed JSON lines should be skipped, not crash replay."""
        path = tmp_path / "test_events.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({"seq": 1, "type": "good", "payload": {}}) + "\n")
            f.write("THIS IS NOT VALID JSON\n")
            f.write(json.dumps({"seq": 3, "type": "good", "payload": {}}) + "\n")
            f.write("{invalid json too\n")
            f.write(json.dumps({"seq": 5, "type": "good", "payload": {}}) + "\n")

        store = EventStore()
        store.open(str(path))
        events = store.replay()

        # Should only get the 3 valid events
        assert len(events) == 3
        assert [e["seq"] for e in events] == [1, 3, 5]
        store.close()

    def test_open_sequence_skips_malformed_lines(self, tmp_path):
        """The open() sequence counter should only count valid JSON lines."""
        path = tmp_path / "test_events.jsonl"
        with open(path, "w") as f:
            f.write(json.dumps({"seq": 1, "type": "good"}) + "\n")
            f.write("MALFORMED LINE\n")
            f.write(json.dumps({"seq": 2, "type": "good"}) + "\n")

        store = EventStore()
        store.open(str(path))
        # Should only count 2 valid lines
        assert store._seq == 2
        store.close()


class TestEventStoreClear:
    def test_clear_removes_file_contents(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("test", {"data": 1})
        store.append("test", {"data": 2})
        assert len(store.replay()) == 2

        store.clear()

        events = store.replay()
        assert len(events) == 0
        store.close()

    def test_clear_resets_sequence(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("test", {})
        store.append("test", {})
        assert store._seq == 2

        store.clear()
        assert store._seq == 0
        store.close()

    def test_clear_allows_new_appends(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)

        store.append("old", {"v": 1})
        store.clear()
        store.append("new", {"v": 2})

        events = store.replay()
        assert len(events) == 1
        assert events[0]["type"] == "new"
        assert events[0]["seq"] == 1  # Reset to 1
        store.close()


class TestEventStoreClose:
    def test_close_clears_file_handle(self, tmp_path):
        store = EventStore()
        path = str(tmp_path / "test_events.jsonl")
        store.open(path)
        assert store._file is not None

        store.close()
        assert store._file is None

    def test_close_without_open_is_safe(self):
        store = EventStore()
        store.close()  # Should not raise
