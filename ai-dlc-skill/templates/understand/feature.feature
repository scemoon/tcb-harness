@FR-{{fr_id}}
Feature: {{feature_name}}

  {{feature_description}}

  @FR-{{fr_id}} @positive
  Scenario: {{positive_scenario_name}}
    Given {{precondition}}
    When {{action}}
    Then {{expected_outcome}}
    And {{additional_outcome}}

  @FR-{{fr_id}} @negative
  Scenario: {{negative_scenario_name}}
    Given {{precondition}}
    When {{action_with_invalid_input}}
    Then {{expected_error}}

  @FR-{{fr_id}} @edge
  Scenario: {{edge_case_scenario_name}}
    Given {{precondition}}
    When {{action_with_boundary_input}}
    Then {{expected_outcome}}

  @FR-{{fr_id}} @logic
  Scenario: {{logic_scenario_name}}
    Given {{precondition_with_state}}
    When {{action}} is repeated multiple times
    Then {{outcome}} remains consistent
    And {{side_effects}} do not accumulate
