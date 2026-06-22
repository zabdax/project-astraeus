import sys
sys.path.append('f:/solo_leveling_assistant/project-astraeus')
from astraeus.core.nasa_archive import NASAExoplanetArchive

meta, err = NASAExoplanetArchive.fetch_metadata("kepler-90")
print("Meta:", meta)
print("Error:", err)
