"""Enriquecimiento opcional de metadatos desde servicios externos."""

from src.enrichment.spotify import EnrichmentReport, enrich_with_spotify

__all__ = ["EnrichmentReport", "enrich_with_spotify"]
