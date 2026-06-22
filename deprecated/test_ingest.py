import sys
import os

# Ensure the package is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from astraeus.core.ingestion import RemoteDiscoveryEngine

print("Testing RemoteDiscoveryEngine...")
result = RemoteDiscoveryEngine.fetch_data("HAT-P-11 b", mission="Kepler")
print("\nFinal Meta Data:")
for k, v in result.get("metadata", {}).items():
    print(f"{k}: {v}")
