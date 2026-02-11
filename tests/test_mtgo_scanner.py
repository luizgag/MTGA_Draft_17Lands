import pytest
import os
import shutil
from src.mtgo_scanner import MtgoScanner, MtgoScannerState
from src.limited_sets import SetDictionary, SetInfo

TEST_DRAFT_LOG = os.path.join(os.getcwd(), "examples", "luluch1-2026.2.6-10252-34431293-ECLECLECL.txt")
TEST_EXAMPLES_DIR = os.path.join(os.getcwd(), "examples")

TEST_SETS = SetDictionary(data={
    "ECL": SetInfo(seventeenlands=["ECL"], set_code="ECL"),
})


@pytest.fixture
def scanner():
    return MtgoScanner(TEST_EXAMPLES_DIR, TEST_SETS)


@pytest.fixture
def mtgo_log_folder(tmp_path):
    """Create a temporary folder with a copy of the test draft log"""
    log_file = tmp_path / "luluch1-2026.2.6-10252-34431293-ECLECLECL.txt"
    shutil.copy2(TEST_DRAFT_LOG, log_file)
    return str(tmp_path)


@pytest.fixture
def scanner_with_folder(mtgo_log_folder):
    return MtgoScanner(mtgo_log_folder, TEST_SETS)


class TestSetCodeExtraction:
    """Test extracting set codes from MTGO draft log filenames"""

    def test_standard_three_pack_same_set(self, scanner):
        """ECLECLECL should extract to ['ECL']"""
        codes = scanner._MtgoScanner__extract_set_codes_from_filename(
            "luluch1-2026.2.6-10252-34431293-ECLECLECL.txt"
        )
        assert codes == ["ECL"]

    def test_mixed_set_codes(self, scanner):
        """ONETWOTHR should extract to ['ONE', 'TWO', 'THR']"""
        codes = scanner._MtgoScanner__extract_set_codes_from_filename(
            "user-2026.1.1-12345-99999999-ONETWOTHR.txt"
        )
        assert codes == ["ONE", "TWO", "THR"]

    def test_lowercase_normalized(self, scanner):
        """lowercase codes should be uppercased"""
        codes = scanner._MtgoScanner__extract_set_codes_from_filename(
            "user-2026.1.1-12345-99999999-ecleclecl.txt"
        )
        assert codes == ["ECL"]

    def test_invalid_length(self, scanner):
        """Non-multiple-of-3 suffix should return empty"""
        codes = scanner._MtgoScanner__extract_set_codes_from_filename(
            "user-2026.1.1-12345-99999999-AB.txt"
        )
        assert codes == []


class TestDraftStartSearch:
    """Test draft detection from the MTGO log folder"""

    def test_detect_new_draft(self, scanner_with_folder):
        """Should detect the draft log file and parse the header"""
        result = scanner_with_folder.draft_start_search()
        assert result is True
        assert scanner_with_folder.draft_sets == ["ECL"]
        assert scanner_with_folder.hero == "luluch1"
        assert scanner_with_folder.draft_type != 0  # Not UNKNOWN

    def test_no_folder(self):
        """Should return False for nonexistent folder"""
        scanner = MtgoScanner("/nonexistent/path", TEST_SETS)
        result = scanner.draft_start_search()
        assert result is False

    def test_empty_folder(self, tmp_path):
        """Should return False for empty folder"""
        scanner = MtgoScanner(str(tmp_path), TEST_SETS)
        result = scanner.draft_start_search()
        assert result is False

    def test_same_file_no_redetect(self, scanner_with_folder):
        """Should not re-detect the same draft file on second call"""
        assert scanner_with_folder.draft_start_search() is True
        assert scanner_with_folder.draft_start_search() is False


class TestDraftDataSearch:
    """Test incremental parsing of draft data"""

    def test_full_log_parsing(self, scanner_with_folder):
        """Should parse all picks from the complete log"""
        scanner_with_folder.draft_start_search()

        # The full log has already been read by draft_start_search (which calls __parse_header)
        # All 42-45 picks should be parsed (3 packs * ~14 picks each)
        assert len(scanner_with_folder.taken_cards) > 0
        assert scanner_with_folder.current_pack == 3

    def test_first_pick_detected(self, scanner_with_folder):
        """The first pick should be 'Ashling, Rekindled'"""
        scanner_with_folder.draft_start_search()
        assert "Ashling, Rekindled" in scanner_with_folder.taken_cards

    def test_taken_cards_accumulate(self, scanner_with_folder):
        """All picks from the complete log should be in taken_cards"""
        scanner_with_folder.draft_start_search()
        # From the example log, known picks:
        expected_picks = [
            "Ashling, Rekindled",
            "Morcant's Eyes",
            "Cinder Strike",
            "Flamekin Gildweaver",
            "Kinsbaile Aspirant",
        ]
        for pick in expected_picks:
            assert pick in scanner_with_folder.taken_cards, f"Expected {pick} in taken cards"


class TestIncrementalParsing:
    """Test two-phase incremental parsing (pack shown then pick made)"""

    def test_phase1_pack_shown(self, tmp_path):
        """Phase 1: Cards appear without a pick marker"""
        log_content = """Event #: 10252
Time:    2/6/2026 8:14:11 PM
Players:
    Player1
--> TestHero

Pack 1 pick 1:
    Card Alpha
    Card Beta
    Card Gamma
"""
        log_file = tmp_path / "test-2026.2.6-10252-12345678-ECLECLECL.txt"
        log_file.write_text(log_content)

        scanner = MtgoScanner(str(tmp_path), TEST_SETS)
        scanner.draft_start_search()

        assert scanner.state == MtgoScannerState.PACK_SHOWN
        assert scanner.pack_cards == ["Card Alpha", "Card Beta", "Card Gamma"]
        assert scanner.current_pack == 1
        assert len(scanner.taken_cards) == 0

    def test_phase2_pick_made(self, tmp_path):
        """Phase 2: Pick marker appears, card moves to taken"""
        log_content = """Event #: 10252
Time:    2/6/2026 8:14:11 PM
Players:
    Player1
--> TestHero

Pack 1 pick 1:
    Card Alpha
--> Card Beta
    Card Gamma

Picked: Card Beta
"""
        log_file = tmp_path / "test-2026.2.6-10252-12345678-ECLECLECL.txt"
        log_file.write_text(log_content)

        scanner = MtgoScanner(str(tmp_path), TEST_SETS)
        scanner.draft_start_search()

        assert scanner.state == MtgoScannerState.PICK_MADE
        assert "Card Beta" in scanner.taken_cards
        # Pack should show remaining cards (excluding picked)
        assert "Card Beta" not in scanner.pack_cards
        assert "Card Alpha" in scanner.pack_cards
        assert "Card Gamma" in scanner.pack_cards

    def test_incremental_file_growth(self, tmp_path):
        """Simulates file growing: first pack shown, then pick appended"""
        # Phase 1: Write pack without pick
        phase1_content = """Event #: 10252
Time:    2/6/2026 8:14:11 PM
Players:
    Player1
--> TestHero

Pack 1 pick 1:
    Card Alpha
    Card Beta
    Card Gamma
"""
        log_file = tmp_path / "test-2026.2.6-10252-12345678-ECLECLECL.txt"
        log_file.write_text(phase1_content)

        scanner = MtgoScanner(str(tmp_path), TEST_SETS)
        scanner.draft_start_search()

        assert scanner.state == MtgoScannerState.PACK_SHOWN
        assert len(scanner.taken_cards) == 0
        assert len(scanner.pack_cards) == 3

        # Phase 2: Append a complete new pack block (realistic MTGO log growth)
        phase2_content = """
------ Pack 1: Test Set ------

Pack 1 pick 2:
    Card Delta
--> Card Epsilon
    Card Zeta

Picked: Card Epsilon
"""
        with open(log_file, 'a') as f:
            f.write(phase2_content)

        result = scanner.draft_data_search()
        assert result is True
        assert "Card Epsilon" in scanner.taken_cards
        assert scanner.state == MtgoScannerState.PICK_MADE


class TestPackTransitions:
    """Test pack number transitions"""

    def test_pack_numbers(self, scanner_with_folder):
        """Pack number should be 3 after parsing the full log (3 packs)"""
        scanner_with_folder.draft_start_search()
        assert scanner_with_folder.current_pack == 3

    def test_pick_counting(self, scanner_with_folder):
        """Total picks should equal the number of taken cards"""
        scanner_with_folder.draft_start_search()
        # Each pack has ~14 picks, 3 packs = ~42 total
        assert len(scanner_with_folder.taken_cards) >= 40


class TestClearDraft:
    """Test draft clearing"""

    def test_clear_draft_partial(self, scanner_with_folder):
        """Partial clear should reset draft state but keep file tracking"""
        scanner_with_folder.draft_start_search()
        file = scanner_with_folder.current_file
        offset = scanner_with_folder.search_offset

        scanner_with_folder.clear_draft(False)

        assert scanner_with_folder.taken_cards == []
        assert scanner_with_folder.current_pack == 0
        assert scanner_with_folder.current_pick == 0
        assert scanner_with_folder.draft_type == 0
        # File tracking preserved
        assert scanner_with_folder.current_file == file

    def test_clear_draft_full(self, scanner_with_folder):
        """Full clear should reset everything"""
        scanner_with_folder.draft_start_search()

        scanner_with_folder.clear_draft(True)

        assert scanner_with_folder.taken_cards == []
        assert scanner_with_folder.current_file == ""
        assert scanner_with_folder.search_offset == 0


class TestRetrieveMethods:
    """Test the retrieve_* methods return proper types"""

    def test_retrieve_current_pack_and_pick(self, scanner_with_folder):
        scanner_with_folder.draft_start_search()
        pack, pick = scanner_with_folder.retrieve_current_pack_and_pick()
        assert isinstance(pack, int)
        assert isinstance(pick, int)
        assert pack >= 1

    def test_retrieve_current_limited_event(self, scanner_with_folder):
        scanner_with_folder.draft_start_search()
        event_set, event_type = scanner_with_folder.retrieve_current_limited_event()
        assert event_set == "ECL"
        assert event_type == "BoosterDraft"

    def test_retrieve_data_sources_no_data(self, scanner_with_folder):
        """Without loaded set data, should return 'None' source"""
        scanner_with_folder.draft_start_search()
        sources = scanner_with_folder.retrieve_data_sources()
        assert isinstance(sources, dict)

    def test_retrieve_taken_cards_returns_list(self, scanner_with_folder):
        """retrieve_taken_cards should return a list (may be empty without dataset)"""
        scanner_with_folder.draft_start_search()
        taken = scanner_with_folder.retrieve_taken_cards()
        assert isinstance(taken, list)

    def test_retrieve_current_pack_cards_returns_list(self, scanner_with_folder):
        """retrieve_current_pack_cards should return a list"""
        scanner_with_folder.draft_start_search()
        pack = scanner_with_folder.retrieve_current_pack_cards()
        assert isinstance(pack, list)

    def test_retrieve_set_metrics(self, scanner_with_folder):
        """retrieve_set_metrics should return a SetMetrics object"""
        scanner_with_folder.draft_start_search()
        metrics = scanner_with_folder.retrieve_set_metrics()
        assert metrics is not None


class TestHindsightNavigation:
    """Test loading a specific MTGO draft file and navigating picks."""

    def test_load_draft_file_builds_history(self, scanner_with_folder):
        files = scanner_with_folder.retrieve_draft_log_files()
        assert files

        assert scanner_with_folder.load_draft_file(files[0]) is True
        assert scanner_with_folder.hindsight_mode is True
        assert len(scanner_with_folder.pick_history) > 0
        assert scanner_with_folder.history_index == 0

    def test_navigate_history_forward_and_backward(self, scanner_with_folder):
        files = scanner_with_folder.retrieve_draft_log_files()
        assert scanner_with_folder.load_draft_file(files[0]) is True

        original_pick = scanner_with_folder.current_pick
        assert scanner_with_folder.navigate_history(1) is True
        assert scanner_with_folder.current_pick >= original_pick

        assert scanner_with_folder.navigate_history(-1) is True
        assert scanner_with_folder.history_index == 0

    def test_navigate_history_stops_at_bounds(self, scanner_with_folder):
        files = scanner_with_folder.retrieve_draft_log_files()
        assert scanner_with_folder.load_draft_file(files[0]) is True

        assert scanner_with_folder.navigate_history(-1) is False

        while scanner_with_folder.navigate_history(1):
            pass

        assert scanner_with_folder.history_index == len(scanner_with_folder.pick_history) - 1
        assert scanner_with_folder.navigate_history(1) is False
