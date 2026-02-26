from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class Archetype(BaseModel):
    """A single draft archetype with card weights."""
    name: str
    color_pair: Optional[str] = None
    auto_weights: bool = True
    cards: Dict[str, float] = Field(default_factory=dict)

class ArchetypeConfig(BaseModel):
    """Full archetype configuration for a set."""
    set_code: str
    detection_threshold: float = 5.0
    scoring_method: str = "simple"
    weight_curve: str = "linear"
    pack_weights: List[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    bayesian_prior: float = 1.0
    opportunity_cost_decay: float = 0.1
    hmm_transition_decay: float = 0.15
    hmm_emission_scale: float = 1.0
    hmm_openness_factor: float = 2.0
    hmm_pick_ramp: int = 5
    rarity_odds: Dict[str, float] = Field(default_factory=lambda: {
        "common": 0.0899,
        "uncommon": 0.0388,
        "rare": 0.0148,
        "mythic": 0.0055,
        "special": 0.0001,
        "bonus": 0.0001,
    })
    card_weight_threshold: float = 0.4
    absence_enabled: bool = True
    slots_per_rarity: Dict[str, int] = Field(default_factory=lambda: {
        "common": 10, "uncommon": 3, "rare": 1, "mythic": 0,
    })
    archetypes: List[Archetype] = Field(default_factory=list)
