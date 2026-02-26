import pytest
from src.archetype_openness import (
    ArchetypeConfig,
    load_archetype_config,
    save_archetype_config,
)

VALID_CONFIG = {
    "set_code": "OTJ",
    "detection_threshold": 5.0,
    "scoring_method": "simple",
    "pack_weights": [1.0, 1.0, 1.0],
    "archetypes": [
        {
            "name": "Golgari",
            "color_pair": "BG",
            "auto_weights": True,
            "cards": {
                "Hardbristle Bandit": 0.85,
                "Shoot the Sheriff": 0.30,
            },
        }
    ],
}


def test_archetype_config_round_trip(tmp_path):
    """Save and reload archetype config via DB, verify equality."""
    db_path = str(tmp_path / "test.db")
    file_path = str(tmp_path / "OTJ_archetypes.json")
    config = ArchetypeConfig.model_validate(VALID_CONFIG)
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded is not None
    assert loaded.set_code == "OTJ"
    assert loaded.archetypes[0].name == "Golgari"
    assert loaded.archetypes[0].cards["Hardbristle Bandit"] == 0.85


def test_load_missing_file_returns_none(tmp_path):
    """Missing set_code in DB returns None gracefully."""
    db_path = str(tmp_path / "test.db")
    loaded = load_archetype_config(str(tmp_path / "NONEXISTENT_archetypes.json"), db_path=db_path)
    assert loaded is None


def test_load_malformed_json_returns_none(tmp_path):
    """set_code absent from DB returns None (replaces old malformed-JSON test)."""
    db_path = str(tmp_path / "test.db")
    from src.database import init_db
    init_db(db_path)
    loaded = load_archetype_config(str(tmp_path / "BAD_archetypes.json"), db_path=db_path)
    assert loaded is None


def test_archetype_config_defaults():
    """Config with minimal fields gets correct defaults."""
    config = ArchetypeConfig(set_code="TST")
    assert config.detection_threshold == 5.0
    assert config.scoring_method == "simple"
    assert config.pack_weights == [1.0, 1.0, 1.0]
    assert config.archetypes == []


def test_hmm_openness_factor_round_trip(tmp_path):
    """hmm_openness_factor persists through save/load."""
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(set_code="TST", hmm_openness_factor=3.0)
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.hmm_openness_factor == 3.0


def test_hmm_pick_ramp_config_round_trip(tmp_path):
    """hmm_pick_ramp persists through save/load."""
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(set_code="TST", hmm_pick_ramp=7)
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.hmm_pick_ramp == 7


def test_weight_curve_round_trip(tmp_path):
    """weight_curve persists through save/load cycle."""
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(set_code="TST", weight_curve="sqrt")
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.weight_curve == "sqrt"


def test_bayesian_prior_round_trip(tmp_path):
    """bayesian_prior persists through save/load cycle."""
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(set_code="TST", bayesian_prior=2.5)
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.bayesian_prior == 2.5


def test_rarity_odds_round_trip(tmp_path):
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(
        set_code="TST",
        rarity_odds={"common": 0.70, "uncommon": 0.50, "rare": 0.40, "mythic": 0.25},
    )
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.rarity_odds["common"] == pytest.approx(0.70)


def test_card_weight_threshold_round_trip(tmp_path):
    """card_weight_threshold persists through save/load cycle."""
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(set_code="TST", card_weight_threshold=0.3)
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.card_weight_threshold == 0.3


def test_bayesian_survival_config_round_trip(tmp_path):
    db_path = str(tmp_path / "test.db")
    config = ArchetypeConfig(
        set_code="TST",
        scoring_method="bayesian_survival",
        absence_enabled=False,
        slots_per_rarity={"common": 11, "uncommon": 3, "rare": 1, "mythic": 0},
    )
    file_path = str(tmp_path / "TST_archetypes.json")
    save_archetype_config(config, file_path, db_path=db_path)
    loaded = load_archetype_config(file_path, db_path=db_path)
    assert loaded.absence_enabled is False
    assert loaded.slots_per_rarity["common"] == 11


class TestConfigDefaults:
    def test_default_weight_curve(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.weight_curve == "linear"

    def test_old_config_without_weight_curve_gets_default(self):
        data = {"set_code": "TST", "scoring_method": "normalized"}
        config = ArchetypeConfig.model_validate(data)
        assert config.weight_curve == "linear"

    def test_default_bayesian_prior(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.bayesian_prior == 1.0

    def test_old_config_without_bayesian_prior_gets_default(self):
        data = {"set_code": "TST", "scoring_method": "simple"}
        config = ArchetypeConfig.model_validate(data)
        assert config.bayesian_prior == 1.0

    def test_default_rarity_odds(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.rarity_odds["common"] == pytest.approx(0.0899)
        assert config.rarity_odds["mythic"] == pytest.approx(0.0055)

    def test_old_config_without_rarity_odds_gets_default(self):
        data = {"set_code": "TST", "scoring_method": "hmm_hybrid"}
        config = ArchetypeConfig.model_validate(data)
        assert config.rarity_odds["uncommon"] == pytest.approx(0.0388)

    def test_hmm_openness_factor_default(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.hmm_openness_factor == 2.0

    def test_old_config_without_hmm_openness_factor_gets_default(self):
        data = {"set_code": "TST", "scoring_method": "hmm_hybrid"}
        config2 = ArchetypeConfig.model_validate(data)
        assert config2.hmm_openness_factor == 2.0

    def test_hmm_pick_ramp_config_default(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.hmm_pick_ramp == 5

    def test_hmm_pick_ramp_old_config_gets_default(self):
        data = {"set_code": "TST", "scoring_method": "hmm_hybrid"}
        config = ArchetypeConfig.model_validate(data)
        assert config.hmm_pick_ramp == 5

    def test_default_absence_enabled(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.absence_enabled is True

    def test_default_slots_per_rarity(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.slots_per_rarity == {
            "common": 10, "uncommon": 3, "rare": 1, "mythic": 0
        }

    def test_old_config_gets_bayesian_survival_defaults(self):
        data = {"set_code": "TST", "scoring_method": "bayesian_survival"}
        config = ArchetypeConfig.model_validate(data)
        assert config.absence_enabled is True
        assert config.slots_per_rarity["common"] == 10

    def test_default_weight_threshold_is_0_4(self):
        config = ArchetypeConfig(set_code="TST")
        assert config.card_weight_threshold == 0.4

    def test_old_config_gets_default_threshold(self):
        data = {"set_code": "TST"}
        config = ArchetypeConfig.model_validate(data)
        assert config.card_weight_threshold == 0.4

    def test_config_default_opportunity_cost_decay(self):
        data = {"set_code": "TST", "scoring_method": "bayesian_beta"}
        config = ArchetypeConfig.model_validate(data)
        assert config.opportunity_cost_decay == 0.1
