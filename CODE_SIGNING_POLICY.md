Code signing policy
===================

Free code signing provided by [SignPath.io](https://about.signpath.io),
certificate by [SignPath Foundation](https://signpath.org).

What is signed
--------------

The installer for Windows (`py-slowdown-VERSION-windows-x64-setup.exe`) is
signed with Authenticode by SignPath Foundation's certificate. It is built
from the source of this repository, at the tag of each release, by the
workflow `.github/workflows/installers.yml` on GitHub's own runners, and it
is sent to SignPath from that same workflow; no installer built anywhere
else is signed. Each signing request is approved by hand.

The libraries that the installer carries (Python, Qt, FFmpeg, NumPy,
Rubber Band and the others, listed with their licences in
[docs/THIRD-PARTY.md](docs/THIRD-PARTY.md)) are not signed by this project:
they are those of their own maintainers.

Apart from that, every file of every release, the installers too, has a
detached signature (`FILE.asc`) made with the project's own GPG key,
[packaging/RPM-GPG-KEY-py-slowdown](packaging/RPM-GPG-KEY-py-slowdown);
see the README.

Team roles
----------

py-slowdown has one maintainer, who holds every role:

- Committers and reviewers: [Nicolas Vaughan](https://github.com/nivaca)
- Approvers: [Nicolas Vaughan](https://github.com/nivaca)

Changes proposed by anyone else (pull requests) are reviewed by him
before they are merged. Multi-factor authentication is used for GitHub and
for SignPath.

Privacy policy
--------------

This program will not transfer any information to other networked systems
unless specifically requested by the user or the person installing or
operating it.

py-slowdown reads and plays the files one opens, and writes its settings,
its bookmarks and the `.slx` of each recording on the computer itself. It
never connects to the internet.
