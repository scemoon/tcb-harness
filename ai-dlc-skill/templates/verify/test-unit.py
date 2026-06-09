"""TDD unit tests for {{feature_name}}.

BDD scenario: {{scenario_ref}}
FR ID: {{fr_id}}
"""

import pytest
from src.{{module}} import {{function_under_test}}


class Test{{feature_class_name}}:
    """TDD cycle: RED → GREEN → REFACTOR."""

    def test_{{positive_case}}(self):
        """RED: Write test → confirm fail. GREEN: Implement → pass."""
        result = {{function_under_test}}({{valid_input}})
        assert result == {{expected_output}}

    def test_{{negative_case}}(self):
        """Negative case: should handle invalid input."""
        with pytest.raises({{expected_exception}}):
            {{function_under_test}}({{invalid_input}})

    def test_{{edge_case}}(self):
        """Edge case: boundary condition."""
        result = {{function_under_test}}({{boundary_input}})
        assert result == {{expected_output}}
