"""
Harmonic Transition Engine using the Camelot Wheel system.

Calculates compatibility, transition costs, and harmonic relationships
between track keys for intelligent set building algorithms.
"""

from enum import Enum
from typing import Tuple, Optional, Dict, List
import re


class StrictnessLevel(str, Enum):
    STRICT = "strict"              # Perfect harmonic matches or adjacent keys only
    ENERGY_BOOST = "energy_boost"  # Allows harmonic jumps (+1, +2 semitones)
    PERMISSIVE = "permissive"      # Allows wider jumps and experimental transitions


class TransitionType(str, Enum):
    PERFECT = "perfect"                # Same key (e.g., 8A -> 8A)
    ADJACENT = "adjacent"              # +/- 1 on Camelot Wheel (e.g., 8A -> 7A / 9A)
    RELATIVE = "relative"              # Same number, A <-> B (e.g., 8A -> 8B)
    ENERGY_BOOST_1 = "energy_boost_1"  # +1 semitone / +7 Camelot numbers (e.g., 8A -> 3A)
    ENERGY_BOOST_2 = "energy_boost_2"  # +2 semitones / +2 Camelot numbers (e.g., 8A -> 10A)
    ENERGY_DROP = "energy_drop"        # -2 Camelot numbers (e.g., 8A -> 6A)
    DIAGONAL = "diagonal"              # +/- 1 and mode switch (e.g., 8A -> 7B)
    DISCORDANT = "discordant"          # Clashing harmonic jump


class CamelotKey:
    """Represents a Camelot Wheel key notation (1A-12A, 1B-12B)."""
    
    # Mapping standard musical keys to Camelot
    STANDARD_TO_CAMELOT = {
        "Abm": "1A", "G#m": "1A", "B": "1B",
        "Ebm": "2A", "D#m": "2A", "F#": "2B", "Gb": "2B",
        "Bbm": "3A", "A#m": "3A", "Db": "3B", "C#": "3B",
        "Fm": "4A", "Ab": "4B",
        "Cm": "5A", "Eb": "5B",
        "Gm": "6A", "Bb": "6B",
        "Dm": "7A", "F": "7B",
        "Am": "8A", "C": "8B",
        "Em": "9A", "G": "9B",
        "Bm": "10A", "D": "10B",
        "F#m": "11A", "G#": "11B", "A": "11B",
        "C#m": "12A", "Dbm": "12A", "E": "12B"
    }

    def __init__(self, key_str: str):
        normalized = self._normalize_key(key_str)
        if not normalized:
            raise ValueError(f"Invalid harmonic key format: '{key_str}'")
        self.number: int = int(normalized[:-1])
        self.letter: str = normalized[-1].upper()
        self.raw: str = f"{self.number}{self.letter}"

    @classmethod
    def _normalize_key(cls, key_str: str) -> Optional[str]:
        """Parses Camelot (8A) or standard music notation (Am, C) into Camelot format."""
        if not key_str or not isinstance(key_str, str):
            return None
            
        clean_key = key_str.strip()
        
        # Check if already Camelot format (e.g., 8A, 12B)
        match = re.match(r"^([1-9]|1[0-2])([a-bA-B])$", clean_key)
        if match:
            num = match.group(1)
            let = match.group(2).upper()
            return f"{num}{let}"
            
        # Try matching standard musical notation
        return cls.STANDARD_TO_CAMELOT.get(clean_key)

    def __str__(self) -> str:
        return self.raw

    def __eq__(self, other) -> bool:
        if isinstance(other, CamelotKey):
            return self.number == other.number and self.letter == other.letter
        return False


def get_camelot_distance(num1: int, num2: int) -> int:
    """Calculates shortest circular distance on the 1-12 Camelot clock."""
    diff = abs(num1 - num2) % 12
    return min(diff, 12 - diff)


def evaluate_harmonic_transition(
    key_from_str: str, 
    key_to_str: str, 
    strictness: StrictnessLevel = StrictnessLevel.ENERGY_BOOST
) -> Tuple[TransitionType, float]:
    """
    Evaluates the transition quality between two keys.
    
    Returns:
        Tuple[TransitionType, float]: The classified transition type and its cost score 
        (0.0 = perfect transition, 10.0 = severe harmonic conflict).
    """
    try:
        k1 = CamelotKey(key_from_str)
        k2 = CamelotKey(key_to_str)
    except ValueError:
        # Penalty for unparseable key data
        return TransitionType.DISCORDANT, 8.0

    # 1. Perfect Match (8A -> 8A)
    if k1 == k2:
        return TransitionType.PERFECT, 0.0

    same_mode = (k1.letter == k2.letter)
    number_diff = (k2.number - k1.number) % 12  # Forward movement on wheel
    clock_distance = get_camelot_distance(k1.number, k2.number)

    # 2. Relative Scale (8A <-> 8B)
    if clock_distance == 0 and not same_mode:
        return TransitionType.RELATIVE, 0.5

    # 3. Adjacent Fifth (+/- 1) (8A -> 7A / 9A)
    if clock_distance == 1 and same_mode:
        return TransitionType.ADJACENT, 0.2

    # 4. Diagonal Transition (8A -> 7B / 9B)
    if clock_distance == 1 and not same_mode:
        return TransitionType.DIAGONAL, 1.5

    # 5. Energy Boost +2 (+2 semitones / +2 numbers) (e.g., 8A -> 10A)
    if number_diff == 2 and same_mode:
        cost = 1.0 if strictness != StrictnessLevel.STRICT else 4.0
        return TransitionType.ENERGY_BOOST_2, cost

    # 6. Energy Boost +1 (+1 semitone / +7 numbers) (e.g., 8A -> 3A)
    if number_diff == 7 and same_mode:
        cost = 2.0 if strictness != StrictnessLevel.STRICT else 6.0
        return TransitionType.ENERGY_BOOST_1, cost

    # 7. Energy Drop (-2 numbers) (e.g., 8A -> 6A)
    if number_diff == 10 and same_mode:  # -2 mod 12 = 10
        cost = 2.5 if strictness == StrictnessLevel.PERMISSIVE else 5.0
        return TransitionType.ENERGY_DROP, cost

    # 8. Discordant / High Cost Jump
    base_cost = 5.0 + (clock_distance * 1.2)
    if strictness == StrictnessLevel.STRICT:
        base_cost += 3.0

    return TransitionType.DISCORDANT, min(base_cost, 10.0)


def calculate_harmonic_cost(
    key_from: str, 
    key_to: str, 
    strictness: str = "energy_boost"
) -> float:
    """
    Helper function returning only the scalar transition cost (0.0 to 10.0).
    Suitable for A* / Dijkstra graph edge weight calculation.
    """
    try:
        level = StrictnessLevel(strictness)
    except ValueError:
        level = StrictnessLevel.ENERGY_BOOST

    _, cost = evaluate_harmonic_transition(key_from, key_to, level)
    return cost


def get_compatible_keys(key_str: str, max_cost: float = 2.5) -> List[str]:
    """Returns a list of Camelot keys compatible with the given key within a cost threshold."""
    compatible = []
    try:
        base_key = CamelotKey(key_str)
    except ValueError:
        return compatible

    all_keys = [f"{num}{let}" for num in range(1, 13) for let in ["A", "B"]]
    
    for candidate in all_keys:
        cost = calculate_harmonic_cost(base_key.raw, candidate)
        if cost <= max_cost:
            compatible.append(candidate)

    return compatible