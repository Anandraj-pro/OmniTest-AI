*** Settings ***
Documentation    Sample suite: API testing + email send/receive with AI content checks.
...              Robot Framework is the PRIMARY authoring layer in OmniTest-AI.
Resource         ../resources/common.resource
Force Tags       sample

*** Test Cases ***
Health Endpoint Is Up
    [Tags]    api    smoke
    Health Check Should Pass

Create User Returns 201 With Valid Body
    [Tags]    api
    ${resp}=    Api Request    POST    ${API_BASE}/users
    ...    json=${{ {"name": "Ada Lovelace", "email": "ada@omnitest.dev"} }}
    Should Be Equal As Integers    ${resp.status}    201
    Response Should Meet Expectation    ${resp}
    ...    Response echoes the created user's name and email and includes an id.

Password Reset Email Arrives With A Reset Link
    [Tags]    email
    Send Email    to=%{OMNI_EMAIL_USER}    subject=OmniTest Reset Probe
    ...    body=Please reset your password using the link below.
    ${msg}=    Wait For Email    subject_contains=OmniTest Reset Probe    timeout=120
    Email Should Meet Expectation    ${msg}
    ...    The email is about a password reset and contains an actionable reset link or instruction.
    ${fields}=    Extract From Email    ${msg}    reset_link    otp
    Log    ${fields}