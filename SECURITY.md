# Security Policy

## Supported versions

Avilys is a small project maintained by one person. Security fixes go into the
latest release only. If you are on an older version, please update first and
check whether the problem is still there.

| Version        | Supported |
| -------------- | --------- |
| Latest release | Yes       |
| Older releases | No        |

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting instead:

1. Go to the [Security tab](https://github.com/anglasligonis/Avilys/security)
   of this repository.
2. Choose **Report a vulnerability**.
3. Describe what you found.

Helpful things to include:

- The Avilys version and your operating system (Windows or Linux, installer,
  AppImage or source).
- What you did, what you expected, and what happened instead.
- A proof of concept, such as a crafted `.torrent` file or magnet link, if you
  have one.
- What you think an attacker could do with it.

## What to expect

- I will acknowledge your report within **7 days**.
- I will tell you whether I can reproduce it and how I plan to handle it,
  usually within **14 days**.
- Fixes for confirmed issues are released as soon as they are ready, and you
  will be credited in the release notes unless you prefer to stay anonymous.
- Please give me reasonable time to fix the problem before you share details
  publicly. I'm happy to agree on a disclosure date with you.

These times are best effort, since this is a volunteer project.

## Scope

In scope:

- Avilys itself: the desktop window, the terminal mode, the installers and
  the AppImage.
- Problems caused by how Avilys handles `.torrent` files, magnet links,
  downloaded file names and paths, settings, or the update check.

Out of scope:

- Bugs in [libtorrent](https://libtorrent.org) or Qt themselves. Please report
  those to their own projects. If Avilys uses them in an unsafe way, that is in
  scope.
- Anything that needs an attacker to already control your computer or your
  user account.
- The content of torrents. Avilys is a transfer tool, and what people share is
  not something I can control.
- Privacy of your IP address in a swarm. Any BitTorrent client shows your IP
  address to the peers you connect to. See the Privacy section of the
  [README](README.md) for what Avilys does and does not hide.
