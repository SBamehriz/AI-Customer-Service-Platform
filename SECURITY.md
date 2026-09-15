# Security policy

## Reporting a vulnerability

Please report anything sensitive privately rather than in a public issue. Use
GitHub's private vulnerability reporting on this repository, under Security,
Report a vulnerability. If that is not available to you, open an issue asking
for a private channel and leave the details out of it.

Please include what you did, what happened, and what you expected instead. A
small reproduction is worth more than a long description.

Anything that is not sensitive is welcome as an ordinary issue.

## Scope

This project has not had a third party security review. It is a platform you
run yourself, so what it handles and what it deliberately does not are written
out in [`docs/security.md`](docs/security.md). Read that before exposing an
install to the internet, and read the deployment checklist at the end of it.

Findings in the following are in scope.

- Authentication, sessions, workspace API keys and the role checks on routes
- Isolation between workspaces
- The unauthenticated widget and portal endpoints
- Webhook signature verification for any channel
- File upload handling and the links that serve files back
- Anything that sends a customer content they should not see

The known gaps in `docs/security.md`, such as there being no audit log, no SSO
and no multi factor authentication, are documented rather than accidental, so
they are not findings on their own. A way around one of the controls that is
claimed to work is.

## Versions

The latest commit on the default branch is the only supported version.
