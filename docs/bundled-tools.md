# Bundled runtime tools

Release archives contain yt-dlp, FFmpeg, ffprobe and Deno. No separate installer,
system Python, Homebrew, administrator access, or PATH changes are needed to use
the bundled tools. Extract the whole archive, keeping its directory structure.
On macOS, drag the whole `.app` to Applications. Source checkouts still use the
Python yt-dlp library and system tools unless configured otherwise.

## Layout and Nuitka

Linux x64 and Windows x64 keep `tools/` beside `YouTubeBootlegger.bin` or
`YouTubeBootlegger.exe`. macOS ARM64 keeps it at
`YouTubeBootlegger.app/Contents/Resources/tools/`.
The tools directory includes `yt-dlp`, `ffmpeg`, `ffprobe`, and `deno` (`.exe` on
Windows), license notices and a manifest of the download URLs and checksums.

The release workflow builds the GUI with pyside6-deploy/Nuitka first, then runs
`scripts/bundle_tools.py` to download and verify native tools. They are independent
processes, not Python modules to compile or files to extract from Nuitka's onefile
payload on every launch. This retains the existing onefile GUI on Linux/Windows;
the distributable is now an archive containing several files. A future MSI/DMG/
Linux package can install exactly the same layout without changing tool lookup.

Lookup uses the original executable path (`sys.argv[0]`, as documented for Nuitka
onefile), never the current working directory or temporary extraction path.
The macOS bundle seal is refreshed after staging tools. Deno's original signature
and JIT entitlements are preserved. Ad-hoc signing is not Apple notarization;
the project still needs Developer ID signing/notarization for a trusted macOS
installer and Windows signing for a signed Windows distribution.

## Tool discovery and overrides

The shared settings layer resolves FFmpeg and yt-dlp in this order:

1. A custom executable path saved in Settings.
2. The executable in the app's bundled `tools/` directory.
3. The command name, resolved by the operating system on PATH.

Fresh release installations default to the bundled yt-dlp executable. Existing
explicit choices of library/external mode are preserved. The bundled Python API
remains available by disabling external mode; removing it from Nuitka compilation
is a separate change. The splitter uses the same FFmpeg resolution as yt-dlp.

Every yt-dlp CLI invocation (download, video info and track sources) receives
`--ffmpeg-location <resolved ffmpeg>` and `--js-runtimes deno:<bundled deno>` when
those tools are bundled/configured. Subprocess argument lists handle spaces and
Windows drive letters without shell quoting. `--ignore-config` prevents a global
yt-dlp config from changing app behavior. Python library mode receives equivalent
`ffmpeg_location` and `js_runtimes` options. ffprobe is beside FFmpeg so yt-dlp
can locate it. Deno falls back to yt-dlp's normal PATH lookup in source checkouts.
Official yt-dlp executables already include the EJS challenge solver scripts.

## Downloads, updates and checks

`scripts/runtime-tools.json` pins URLs and SHA256 hashes for each architecture:

| Tool | Provider/version |
| --- | --- |
| yt-dlp | Official yt-dlp release 2026.10.26; Linux x64, Windows x64, universal macOS |
| FFmpeg + ffprobe (Linux/Windows) | yt-dlp/FFmpeg-Builds autobuild-2026-10-29-00-02 |
| FFmpeg + ffprobe (macOS ARM) | OSXExperts FFmpeg 9.0 ARM builds |
| Deno | Official Deno v2.9.8; native architecture on each OS |

All downloads are verified against pinned archive/executable hashes. OSXExperts
also publishes hashes of the extracted binaries, which are verified after copying
only the expected regular file from each ZIP. Arbitrary archive paths, links, and
duplicate executable names are not extracted. A failed check leaves no tools
directory. Updating tools means reviewing and changing the manifest; the app does
not self-update these managed binaries at runtime.

The download script runs each tool, checks Deno can execute JavaScript, records
FFmpeg's build license, and checks yt-dlp accepts the explicit companion paths. The
native CI matrix also tests FFmpeg conversion, ffprobe and app lookup from an
unrelated working directory. A compiled Nuitka probe also verifies executable discovery in onefile mode and
in a macOS app bundle. These checks are offline and do not guarantee that
YouTube will accept a particular video/account/network.

## Third-party licenses and source distribution

These are separate third-party executables, not MIT-relicensed components.
Official standalone yt-dlp and the selected FFmpeg builds include GPL code. Deno
is MIT with additional dependency notices. Included license texts and manifests
document these components; notices alone do not satisfy GPL corresponding-source
requirements. Before distributing a release, its publisher must also provide the
complete corresponding source and build information for the exact GPL/LGPL
binaries and their included dependencies through a license-compliant method.
Upstream links alone are not a substitute for the publisher's obligations.
This PR's packaging automation does not construct that source distribution or
claim a complete transitive third-party license audit of the downloaded binaries.

The script refuses FFmpeg builds configured with `--enable-nonfree`. The existing
Mutagen and Qt/PySide dependencies have their own licensing obligations; this
packaging work does not remove Mutagen or make the application permissively
licensed. A closed-source release needs the separate dependency/license work
discussed before this PR.

References:

- https://github.com/yt-dlp/yt-dlp#licensing
- https://github.com/yt-dlp/yt-dlp/wiki/EJS
- https://www.ffmpeg.org/legal.html
- https://github.com/denoland/deno/blob/v2.9.8/LICENSE.md
- https://nuitka.net/user-documentation/common-issue-solutions.html#onefile-finding-files
