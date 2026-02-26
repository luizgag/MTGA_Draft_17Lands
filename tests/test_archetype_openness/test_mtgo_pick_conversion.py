import pytest


class TestMtgoPickConversion:
    """Tests verifying MTGO pick-in-pack vs Arena pick behavior."""

    def test_arena_pick_is_per_pack(self, tmp_path):
        """ArenaScanner.retrieve_current_pick_in_pack returns current_pick (already per-pack)."""
        from src.log_scanner import ArenaScanner
        scanner = ArenaScanner(str(tmp_path / "Player.log"), set_list=[])
        scanner.current_pick = 5
        assert scanner.retrieve_current_pick_in_pack() == 5

    def test_mtgo_pick_in_pack_resets(self, tmp_path):
        """MtgoScanner.retrieve_current_pick_in_pack returns per-pack pick, not sequential."""
        from src.mtgo_scanner import MtgoScanner
        scanner = MtgoScanner(str(tmp_path), set_list=[])
        scanner.current_pick_in_pack = 3
        assert scanner.retrieve_current_pick_in_pack() == 3

    def test_mtgo_sequential_vs_per_pack(self, tmp_path):
        """MTGO current_pick is sequential (16 for P2P1), but pick_in_pack is 1."""
        from src.mtgo_scanner import MtgoScanner
        scanner = MtgoScanner(str(tmp_path), set_list=[])
        # Simulate P2P1: sequential pick is 16, but pick_in_pack is 1
        scanner.current_pick = 16
        scanner.current_pick_in_pack = 1
        assert scanner.retrieve_current_pick_in_pack() == 1
        # The openness tracker should use 1, not 16
