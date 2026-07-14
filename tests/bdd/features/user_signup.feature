Feature: User signup
  As a new user I can create an account and receive a welcome email.

  # Every step below already exists in steps/common_steps.py — this feature
  # needed ZERO new Python. That is the pattern to aim for at 50+ stories.

  @api @smoke
  Scenario: Create a user via the API
    Given the API base url is "https://api.example.com"
    When I POST "/users" with a fake user
    Then the response status should be 201
    And the response body should have "id"
    And the response should be semantically valid

  @email
  Scenario: New user receives a welcome email
    When I send an email to "new.user@example.com" with subject "Welcome"
    And I wait for an email with subject "Welcome"
    Then the email should convey "how to get started with the account"
