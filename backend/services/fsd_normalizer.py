class FSDNormalizer:
    """
    Validates and normalizes Full Self-Driving (FSD) segments according to the 
    Agentic SQL Vector System specification.
    """
    
    # A simplified normalization coefficient model
    # Weights for external variables (must sum to 1.0)
    TRAFFIC_WEIGHT = 0.5
    WEATHER_WEIGHT = 0.3
    TERRAIN_WEIGHT = 0.2

    @staticmethod
    def is_valid_segment(fsd_percentage: float) -> bool:
        """Enforces the >= 99% continuous FSD rule for vectorization eligibility."""
        return fsd_percentage >= 0.99
    
    @staticmethod
    def normalize_metrics(fsd_percentage: float, traffic_density: float, weather_severity: float, terrain_complexity: float) -> float:
        """
        Adjusts the FSD percentage based on environmental difficulty.
        If difficulty is higher, the normalized achievement is scored higher.
        Variables must be normalized between 0.0 (easiest) and 1.0 (hardest).
        """
        if not FSDNormalizer.is_valid_segment(fsd_percentage):
            raise ValueError("Segment must be >= 99% FSD to be canonical and vectorizable.")
            
        # Ensure inputs are clamped 0.0 -> 1.0
        traffic = max(0.0, min(1.0, traffic_density))
        weather = max(0.0, min(1.0, weather_severity))
        terrain = max(0.0, min(1.0, terrain_complexity))
            
        difficulty_score = (traffic * FSDNormalizer.TRAFFIC_WEIGHT) + \
                           (weather * FSDNormalizer.WEATHER_WEIGHT) + \
                           (terrain * FSDNormalizer.TERRAIN_WEIGHT)
                           
        # The harder the conditions, the more impressive the 99%+ score.
        # This applies a difficulty multiplier. For maximum difficulty (1.0),
        # score is boosted by 5% (0.05).
        difficulty_modifier = 1.0 + (difficulty_score * 0.05)
        
        normalized_score = fsd_percentage * difficulty_modifier
        
        # Output cannot exceed 1.0 (100% normalized achievement)
        return min(normalized_score, 1.0)
