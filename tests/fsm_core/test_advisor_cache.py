"""Tests for advisor_cache: hash determinism, lookup, store, and round-trip."""

from datetime import UTC, datetime
from pathlib import Path

from src.fsm_core.advisor_cache import (
    ADVISOR_PROMPT_VERSION,
    CachedVerdict,
    WaveHashInput,
    clear_cache,
    compute_wave_hash,
    lookup_verdict,
    store_verdict,
)


class TestComputeWaveHashDeterministic:
    """Hash computation must be deterministic."""

    def test_compute_wave_hash_is_deterministic(self) -> None:
        """Same input twice produces identical hash."""
        wave_input = WaveHashInput(
            prompt_version=1,
            model="claude-opus-4",
            task_paths=("task_001.md", "task_002.md"),
            file_hashes=(
                ("file1.py", "abc123"),
                ("file2.py", "def456"),
            ),
        )
        hash1 = compute_wave_hash(wave_input)
        hash2 = compute_wave_hash(wave_input)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex is 64 chars


class TestComputeWaveHashVersionSensitivity:
    """Hash changes when ADVISOR_PROMPT_VERSION changes."""

    def test_compute_wave_hash_differs_on_prompt_version_bump(
        self,
    ) -> None:
        """Bumping prompt_version in input invalidates the hash."""
        base_input = WaveHashInput(
            prompt_version=ADVISOR_PROMPT_VERSION,
            model="claude-opus-4",
            task_paths=("task_001.md",),
            file_hashes=(("file.py", "abc123"),),
        )
        bumped_input = WaveHashInput(
            prompt_version=ADVISOR_PROMPT_VERSION + 1,
            model="claude-opus-4",
            task_paths=("task_001.md",),
            file_hashes=(("file.py", "abc123"),),
        )
        hash_base = compute_wave_hash(base_input)
        hash_bumped = compute_wave_hash(bumped_input)
        assert hash_base != hash_bumped


class TestComputeWaveHashFileSensitivity:
    """Hash changes when file hashes change."""

    def test_compute_wave_hash_differs_on_file_sha_change(self) -> None:
        """Changing one file hash invalidates the wave hash."""
        input1 = WaveHashInput(
            prompt_version=1,
            model="claude-opus-4",
            task_paths=("task.md",),
            file_hashes=(("file.py", "hash_old"),),
        )
        input2 = WaveHashInput(
            prompt_version=1,
            model="claude-opus-4",
            task_paths=("task.md",),
            file_hashes=(("file.py", "hash_new"),),
        )
        hash1 = compute_wave_hash(input1)
        hash2 = compute_wave_hash(input2)
        assert hash1 != hash2


class TestLookupVerdictMiss:
    """Lookup returns None on cache miss."""

    def test_lookup_verdict_returns_none_on_miss(self, tmp_path: Path) -> None:
        """Empty cache dir returns None."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        result = lookup_verdict("nonexistent_hash", cache_dir)
        assert result is None


class TestStoreAndLookupRoundTrip:
    """Store-then-lookup round-trip preserves verdict data."""

    def test_store_then_lookup_round_trip(self, tmp_path: Path) -> None:
        """Store APPROVE verdict, lookup returns identical CachedVerdict."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        wave_hash = "abc123def456"
        now_iso = datetime.now(UTC).isoformat()
        stored_entry = CachedVerdict(
            wave_hash=wave_hash,
            verdict="APPROVE",
            timestamp_iso=now_iso,
            task_ids=("task_001", "task_002"),
            schema_version=1,
        )

        # Store the verdict
        success = store_verdict(stored_entry, cache_dir)
        assert success is True

        # Verify the file was written
        cache_file = cache_dir / f"{wave_hash}.json"
        assert cache_file.exists()

        # Lookup and verify round-trip
        retrieved = lookup_verdict(wave_hash, cache_dir)
        assert retrieved is not None
        assert retrieved.wave_hash == stored_entry.wave_hash
        assert retrieved.verdict == stored_entry.verdict
        assert retrieved.timestamp_iso == stored_entry.timestamp_iso
        assert retrieved.task_ids == stored_entry.task_ids
        assert retrieved.schema_version == stored_entry.schema_version


class TestStoreVerdictRejectsRevise:
    """REVISE verdicts are never cached — store_verdict rejects them."""

    def test_store_verdict_rejects_revise(self, tmp_path: Path) -> None:
        """Attempt to store REVISE verdict returns False and writes no file."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        wave_hash = "revise_hash_123"
        now_iso = datetime.now(UTC).isoformat()
        revise_entry = CachedVerdict(
            wave_hash=wave_hash,
            verdict="REVISE",
            timestamp_iso=now_iso,
            task_ids=("task_001",),
            schema_version=1,
        )

        # Attempt to store REVISE verdict
        success = store_verdict(revise_entry, cache_dir)
        assert success is False

        # Verify no file was written
        cache_file = cache_dir / f"{wave_hash}.json"
        assert not cache_file.exists()


class TestClearCacheRemovesAllJsonFiles:
    """clear_cache removes all .json files and returns count."""

    def test_clear_cache_removes_all_json_files(self, tmp_path: Path) -> None:
        """Populate cache_dir with .json files, clear_cache removes all."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        # Create a few cached verdict files
        verdicts = [
            CachedVerdict(
                wave_hash="hash_001",
                verdict="APPROVE",
                timestamp_iso=datetime.now(UTC).isoformat(),
                task_ids=("task_001",),
                schema_version=1,
            ),
            CachedVerdict(
                wave_hash="hash_002",
                verdict="APPROVE",
                timestamp_iso=datetime.now(UTC).isoformat(),
                task_ids=("task_002",),
                schema_version=1,
            ),
            CachedVerdict(
                wave_hash="hash_003",
                verdict="APPROVE",
                timestamp_iso=datetime.now(UTC).isoformat(),
                task_ids=("task_003",),
                schema_version=1,
            ),
        ]

        # Store all verdicts
        for verdict in verdicts:
            success = store_verdict(verdict, cache_dir)
            assert success is True

        # Verify files were written
        assert len(list(cache_dir.glob("*.json"))) == 3

        # Clear the cache
        deleted_count = clear_cache(cache_dir)
        assert deleted_count == 3

        # Verify directory is empty
        assert len(list(cache_dir.glob("*.json"))) == 0


class TestPromptVersionBumpInvalidatesCache:
    """Bumping ADVISOR_PROMPT_VERSION invalidates cached verdicts."""

    def test_prompt_version_bump_invalidates_cache(self, tmp_path: Path) -> None:
        """Store under version N, rebuild with N+1, old hash resolves to None."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()

        # Store a verdict with current prompt version
        base_input = WaveHashInput(
            prompt_version=ADVISOR_PROMPT_VERSION,
            model="claude-opus-4",
            task_paths=("task_001.md",),
            file_hashes=(("file.py", "abc123"),),
        )
        base_hash = compute_wave_hash(base_input)

        stored_entry = CachedVerdict(
            wave_hash=base_hash,
            verdict="APPROVE",
            timestamp_iso=datetime.now(UTC).isoformat(),
            task_ids=("task_001",),
            schema_version=1,
        )
        success = store_verdict(stored_entry, cache_dir)
        assert success is True

        # Verify the cached entry is retrievable
        retrieved = lookup_verdict(base_hash, cache_dir)
        assert retrieved is not None

        # Now simulate a prompt version bump
        bumped_input = WaveHashInput(
            prompt_version=ADVISOR_PROMPT_VERSION + 1,
            model="claude-opus-4",
            task_paths=("task_001.md",),
            file_hashes=(("file.py", "abc123"),),
        )
        bumped_hash = compute_wave_hash(bumped_input)

        # The bumped hash must be different
        assert base_hash != bumped_hash

        # Looking up with the new hash should find nothing
        # (the cache still has the old hash, but we're querying with the new one)
        retrieved_bumped = lookup_verdict(bumped_hash, cache_dir)
        assert retrieved_bumped is None
        assert lookup_verdict(base_hash, cache_dir) is not None  # orphaned but still on disk
