*** Settings ***
Documentation    Shared setup for OmniTest-AI Robot suites (the primary test layer).
Library          omnitest.robot.OmniAI
Library          Collections

*** Variables ***
${API_BASE}      %{OMNI_API_BASE_URL=https://api.example.com}

*** Keywords ***
Health Check Should Pass
    [Documentation]    Example reusable keyword combining API + AI verification.
    ${resp}=    Api Request    GET    ${API_BASE}/health
    Should Be Equal As Integers    ${resp.status}    200
    Response Should Meet Expectation    ${resp}
    ...    Body indicates the service is healthy / up.