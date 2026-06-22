import pytest
import sys

with open('pytest_pipeline.log', 'w') as f:
    sys.stdout = f
    sys.stderr = f
    pytest.main(['-v', 'tests/pipeline_stress_test.py'])
