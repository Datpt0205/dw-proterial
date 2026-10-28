"""Gather the third-party licence notices a hand-over ships with.

Apache-2.0, MIT and BSD require their notices to travel with every copy, and
GPL-2.0 a source offer, so a deployment handed to a customer carries them all.
They are read from the BUILT images, never from a developer's checkout: the
images are what the customer receives, and a dev environment also holds tools
that never ship (pytest, ruff, mypy).

    $(COMPOSE) <on-prem files> --profile full config --images \
        | uv run python scripts/third_party_notices.py --out dist/third-party-notices

What it writes:
- ``danh-muc-thanh-phan.xlsx``: one row per component and version, the images
  it ships in, its licence and where its text sits in the folder;
- ``licenses/``: each component's own licence and NOTICE files, as shipped;
- ``README.txt``: how the folder is laid out, and the GPL source offer.

Our own images (``dw-*``) are opened and read package by package. A
third-party image is pulled by the customer unmodified, so it is listed with
its project's own licence, fetched at the pinned tag; it carries its inner
components' notices itself. Run on a machine with internet: it fetches those
licences, the web's npm licences come from this checkout's pnpm store (the
same lockfile the image was built from), and SPDX texts stand in where a
package ships no licence file of its own, marked as such in the catalogue.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from email.parser import Parser
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.worksheet import Worksheet

ROOT = Path(__file__).resolve().parents[1]
SPDX_TAG = "v3.27.0"  # spdx/license-list-data, pinned
OWN = re.compile(r"^(dw[-_]|@dw/)")
LICENCE_FILE = re.compile(r"^(licen[cs]e|copying|notice|authors|copyright)", re.I)

# Where a third-party image's project keeps its licence, keyed by image
# repository: (GitHub repo, image tag -> git tag, licence path, SPDX id).
UPSTREAM: dict[str, tuple[str, Callable[[str], str], str, str]] = {
    "caddy": ("caddyserver/caddy", lambda t: "v" + t.split("-")[0], "LICENSE", "Apache-2.0"),
    "chrislusf/seaweedfs": ("seaweedfs/seaweedfs", lambda t: t, "LICENSE", "Apache-2.0"),
    "clamav/clamav": ("Cisco-Talos/clamav", lambda t: "clamav-" + t, "COPYING.txt", "GPL-2.0-only"),
    "ghcr.io/ggml-org/llama.cpp": (
        "ggml-org/llama.cpp",
        lambda t: t.split("-")[-1],
        "LICENSE",
        "MIT",
    ),
    "ollama/ollama": ("ollama/ollama", lambda t: "v" + t, "LICENSE", "MIT"),
    "postgres": (
        "postgres/postgres",
        lambda t: "REL_" + t.split("-")[0].replace(".", "_"),
        "COPYRIGHT",
        "PostgreSQL",
    ),
    "qdrant/qdrant": ("qdrant/qdrant", lambda t: t, "LICENSE", "Apache-2.0"),
    "quay.io/keycloak/keycloak": ("keycloak/keycloak", lambda t: t, "LICENSE.txt", "Apache-2.0"),
    "rclone/rclone": ("rclone/rclone", lambda t: "v" + t, "COPYING", "MIT"),
    "valkey/valkey": ("valkey-io/valkey", lambda t: t.split("-")[0], "COPYING", "BSD-3-Clause"),
}

# The models the on-prem stack loads (infra/onprem/fetch-models.sh pulls
# them): (name, version, licence, model page, licence file URL or None when
# the repository has none and the page's licence tag is the statement).
MODELS = [
    (
        "Qwen3.5-9B (Ollama qwen3.5:9b)",
        "9B",
        "Apache-2.0",
        "https://huggingface.co/Qwen/Qwen3.5-9B",
        "https://huggingface.co/Qwen/Qwen3.5-9B/raw/main/LICENSE",
    ),
    ("bge-m3 (Ollama bge-m3:567m)", "567m", "MIT", "https://huggingface.co/BAAI/bge-m3", None),
    (
        "bge-reranker-v2-m3 (GGUF Q8_0, gpustack)",
        "v2-m3",
        "Apache-2.0",
        "https://huggingface.co/BAAI/bge-reranker-v2-m3",
        None,
    ),
]

# A Python package that ships no licence file in its wheel, but whose text
# this repository holds.
VENDORED = {"brandkit": ROOT / "vendor" / "brandkit"}

# Licence words in metadata, as SPDX ids, for a package that needs a stand-in text.
CLASSIFIER_SPDX = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
}


@dataclass
class Component:
    kind: str
    name: str
    version: str
    licence: str
    source: str = ""
    images: set[str] = field(default_factory=set)
    files: list[str] = field(default_factory=list)  # paths inside the output folder
    stand_in: bool = False  # the text is SPDX's, the package shipped none


class Catalogue:
    def __init__(self, out: Path) -> None:
        self.out = out
        self.items: dict[tuple[str, str, str], Component] = {}
        self.spdx_needed: set[str] = set()

    def add(self, c: Component, image: str) -> Component:
        key = (c.kind, c.name.lower(), c.version)
        kept = self.items.setdefault(key, c)
        kept.images.add(image)
        return kept

    def write(self, rel: str, data: bytes) -> str:
        path = self.out / "licenses" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return "licenses/" + rel

    def stand_in(self, c: Component, licence: str) -> None:
        ids = (
            [CLASSIFIER_SPDX.get(licence, licence)]
            if licence in CLASSIFIER_SPDX
            else spdx_ids(licence)
        )
        for i in ids:
            self.spdx_needed.add(i)
            c.files.append(f"licenses/spdx/{i}.txt")
        c.stand_in = True


def spdx_ids(expr: str) -> list[str]:
    tokens = re.split(r"[\s()]+|\bAND\b|\bOR\b|\bWITH\b", expr)
    return [
        t
        for t in tokens
        if re.fullmatch(r"[A-Za-z0-9.+-]+", t or "") and t not in {"AND", "OR", "WITH"}
    ]


def fetch(url: str) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return bytes(r.read())
    except Exception as exc:
        print(f"  could not fetch {url}: {exc}", file=sys.stderr)
        return None


def image_tar(image: str, script: str) -> tarfile.TarFile:
    raw = subprocess.run(
        ["docker", "run", "--rm", "--user", "0", "--entrypoint", "sh", image, "-c", script],
        check=True,
        capture_output=True,
    ).stdout
    return tarfile.open(fileobj=io.BytesIO(raw))


def members(tar: tarfile.TarFile) -> dict[str, bytes]:
    out = {}
    for m in tar.getmembers():
        # A file reached twice (a doc folder that is a symlink to another
        # package's) is stored the second time as a hard link.
        if m.isfile() or m.islnk():
            f = tar.extractfile(m)
            if f is not None:
                out[m.name] = f.read()
    return out


PY_SCRIPT = r"""
cd / &&
dpkg-query -W -f='${Package}\t${Version}\n' > /tmp/dpkg.tsv &&
{ echo tmp/dpkg.tsv;
  ls usr/share/doc/*/copyright;
  ls usr/local/lib/python3.12/LICENSE.txt 2>/dev/null;
  find app/.venv/lib/python3.12/site-packages -maxdepth 5 -type f -path '*.dist-info/*' \
    \( -name METADATA -o -path '*/licenses/*' -o -iname 'LICEN[CS]E*' -o -iname 'COPYING*' \
       -o -iname 'NOTICE*' -o -iname 'AUTHORS*' \); } > /tmp/list &&
tar cf - -T /tmp/list
"""

WEB_SCRIPT = r"""
cd / &&
apk list -I > /tmp/apk.txt 2>/dev/null &&
{ echo tmp/apk.txt;
  find app usr/local/lib/node_modules -maxdepth 9 -type f -path '*node_modules*' \
    \( -name package.json -o -iname 'LICEN[CS]E*' -o -iname 'NOTICE*' -o -iname 'COPYING*' \);
} > /tmp/list &&
tar cf - -T /tmp/list
"""


def dep5_licences(text: str) -> str:
    found = []
    for line in text.splitlines():
        if line.startswith("License:"):
            name = line.split(":", 1)[1].strip()
            if name and name not in found:
                found.append(name)
    return " / ".join(found[:6]) or "xem file copyright"


def python_image(cat: Catalogue, image: str) -> None:
    files = members(image_tar(image, PY_SCRIPT))
    for line in files["tmp/dpkg.tsv"].decode().splitlines():
        pkg, version = line.split("\t")
        copyright_ = files.get(f"usr/share/doc/{pkg}/copyright")
        c = cat.add(
            Component(
                "Debian",
                pkg,
                version,
                dep5_licences(copyright_.decode("utf-8", "replace")) if copyright_ else "?",
                f"https://packages.debian.org/bookworm/{pkg}",
            ),
            image,
        )
        if copyright_ and not c.files:
            c.files.append(cat.write(f"debian/{pkg}/copyright", copyright_))
    cpython = files.get("usr/local/lib/python3.12/LICENSE.txt")
    if cpython:
        c = cat.add(
            Component("Runtime", "CPython", "3.12", "PSF-2.0", "https://www.python.org/"), image
        )
        if not c.files:
            c.files.append(cat.write("runtime/cpython-3.12/LICENSE.txt", cpython))

    by_dist: dict[str, dict[str, bytes]] = {}
    for name, data in files.items():
        m = re.match(r"app/\.venv/lib/python3\.12/site-packages/([^/]+\.dist-info)/(.+)", name)
        if m:
            by_dist.setdefault(m.group(1), {})[m.group(2)] = data
    for parts in by_dist.values():
        meta = Parser().parsestr(parts.get("METADATA", b"").decode("utf-8", "replace"))
        name, version = meta["Name"], meta["Version"]
        if not name or OWN.match(name):
            continue
        classifiers = [
            c.split("::")[-1].strip()
            for c in meta.get_all("Classifier") or []
            if c.startswith("License ::")
        ]
        licence = (meta.get("License-Expression") or "").strip() or "; ".join(classifiers)
        if not licence:
            raw = (meta.get("License") or "").strip()
            licence = raw.splitlines()[0][:80] if raw else "?"
        urls = [u.split(",", 1)[-1].strip() for u in meta.get_all("Project-URL") or []]
        c = cat.add(
            Component(
                "Python",
                name,
                version,
                licence,
                meta.get("Home-page") or (urls[0] if urls else f"https://pypi.org/project/{name}/"),
            ),
            image,
        )
        if c.files:
            continue
        for rel, data in sorted(parts.items()):
            if rel != "METADATA" and rel not in {"RECORD", "WHEEL"}:
                c.files.append(cat.write(f"python/{name}-{version}/{rel}", data))
        vendored = VENDORED.get(name.lower())
        if not c.files and vendored:
            for f in sorted(vendored.iterdir()):
                if f.is_file() and LICENCE_FILE.match(f.name):
                    c.files.append(cat.write(f"python/{name}-{version}/{f.name}", f.read_bytes()))
        if not c.files:
            cat.stand_in(c, licence)


def npm_licence(pkg: dict[str, object]) -> str:
    lic = pkg.get("license") or pkg.get("licenses") or "?"
    if isinstance(lic, dict):
        lic = lic.get("type", "?")
    if isinstance(lic, list):
        lic = " OR ".join(x.get("type", "?") if isinstance(x, dict) else str(x) for x in lic)
    return str(lic)


def store_texts(name: str, version: str) -> dict[str, bytes]:
    """The package's licence files from this checkout's pnpm store, same version:
    Next's standalone output copies the code a server needs and drops them."""
    store = ROOT / "node_modules" / ".pnpm"
    for d in store.glob(f"{name.replace('/', '+')}@{version}*/node_modules/{name}"):
        return {
            f.name: f.read_bytes()
            for f in d.iterdir()
            if f.is_file() and LICENCE_FILE.match(f.name)
        }
    return {}


def npm_component(
    cat: Catalogue,
    image: str,
    name: str,
    version: str,
    licence: str,
    home: str,
    texts: dict[str, bytes],
) -> None:
    c = cat.add(
        Component("npm", name, version, licence, home or f"https://www.npmjs.com/package/{name}"),
        image,
    )
    if c.files:
        return
    texts = texts or store_texts(name, version)
    safe = name.replace("/", "__")
    for fname, data in sorted(texts.items()):
        c.files.append(cat.write(f"npm/{safe}-{version}/{fname}", data))
    if not c.files:
        cat.stand_in(c, licence)


def web_image(cat: Catalogue, image: str) -> None:
    files = members(image_tar(image, WEB_SCRIPT))
    for line in files["tmp/apk.txt"].decode().splitlines():
        m = re.match(r"(\S+)-(\d\S*-r\d+) \S+ \{(\S+)\} \((.+)\) \[installed\]", line)
        if m:
            c = cat.add(
                Component(
                    "Alpine",
                    m.group(1),
                    m.group(2),
                    m.group(4),
                    f"https://pkgs.alpinelinux.org/packages?name={m.group(1)}",
                ),
                image,
            )
            if not c.files:
                cat.stand_in(c, m.group(4))
    node = fetch(f"https://raw.githubusercontent.com/nodejs/node/v{node_version(image)}/LICENSE")
    c = cat.add(
        Component(
            "Runtime",
            "Node.js",
            node_version(image),
            "MIT (và các thành phần đi kèm, xem file)",
            "https://nodejs.org/",
        ),
        image,
    )
    if node and not c.files:
        c.files.append(cat.write(f"runtime/nodejs-{c.version}/LICENSE", node))

    # Packages the image holds as files (Next's standalone server, corepack).
    for name, data in files.items():
        m = re.match(r"(.*node_modules/((?:@[^/]+/)?[^/]+))/package\.json$", name)
        if not m:
            continue
        pkg = json.loads(data)
        if pkg.get("name") != m.group(2) or not pkg.get("version") or OWN.match(pkg["name"]):
            continue
        texts = {
            n.rsplit("/", 1)[1]: d
            for n, d in files.items()
            if n.startswith(m.group(1) + "/")
            and n.count("/") == m.group(1).count("/") + 1
            and LICENCE_FILE.match(n.rsplit("/", 1)[1])
        }
        npm_component(
            cat,
            image,
            pkg["name"],
            pkg["version"],
            npm_licence(pkg),
            pkg.get("homepage", ""),
            texts,
        )

    # Everything else the build compiled into its bundles: the web's
    # production dependencies, from the lockfile the image was built from.
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        sys.exit("pnpm is needed for the web's production dependencies")
    listing = json.loads(
        subprocess.run(
            [pnpm, "licenses", "list", "--prod", "--long", "--json"],
            cwd=ROOT / "apps" / "web",
            check=True,
            capture_output=True,
            encoding="utf-8",
        ).stdout
    )
    for licence, pkgs in listing.items():
        for p in pkgs:
            # This checkout's own platform binaries; the image holds its own (linuxmusl).
            if OWN.match(p["name"]) or re.search(r"-(win32|darwin)-", p["name"]):
                continue
            for version, path in zip(p["versions"], p["paths"], strict=False):
                texts = {
                    f.name: f.read_bytes()
                    for f in Path(path).iterdir()
                    if f.is_file() and LICENCE_FILE.match(f.name)
                }
                npm_component(cat, image, p["name"], version, licence, p.get("homepage", ""), texts)


def node_version(image: str, _cache: dict[str, str] = {}) -> str:  # noqa: B006 - one lookup per image
    if image not in _cache:
        _cache[image] = (
            subprocess.run(
                ["docker", "run", "--rm", "--entrypoint", "node", image, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            .stdout.strip()
            .lstrip("v")
        )
    return _cache[image]


def third_party_image(cat: Catalogue, ref: str) -> None:
    ref = ref.split("@", 1)[0]
    repo, _, tag = ref.rpartition(":")
    known = UPSTREAM.get(repo)
    if known is None:
        sys.exit(f"no upstream licence known for image {ref}: add it to UPSTREAM")
    gh, to_tag, path, spdx = known
    git_tag = to_tag(tag)
    c = cat.add(Component("Image", repo, tag, spdx, f"https://github.com/{gh}/tree/{git_tag}"), ref)
    text = fetch(f"https://raw.githubusercontent.com/{gh}/{git_tag}/{path}")
    if text:
        c.files.append(cat.write(f"images/{repo.replace('/', '__')}-{tag}/{path}", text))
    else:
        cat.stand_in(c, spdx)


def models(cat: Catalogue) -> None:
    for name, version, licence, page, url in MODELS:
        c = cat.add(Component("Model", name, version, licence, page), "ollama / llama.cpp")
        text = fetch(url) if url else None
        if text:
            c.files.append(
                cat.write(f"models/{re.sub(r'[^A-Za-z0-9.-]+', '_', name)}/LICENSE", text)
            )
        else:
            cat.stand_in(c, licence)


def spdx_texts(cat: Catalogue) -> list[str]:
    missing = []
    for i in sorted(cat.spdx_needed):
        text = fetch(
            f"https://raw.githubusercontent.com/spdx/license-list-data/{SPDX_TAG}/text/{i}.txt"
        )
        if text:
            cat.write(f"spdx/{i}.txt", text)
        else:
            missing.append(i)
    return missing


KIND_ORDER = ["Model", "Image", "Runtime", "Python", "npm", "Debian", "Alpine"]
KIND_LABEL = {
    "Model": "Mô hình AI",
    "Image": "Image bên thứ ba",
    "Runtime": "Môi trường chạy",
    "Python": "Thư viện Python",
    "npm": "Thư viện JavaScript",
    "Debian": "Gói hệ điều hành (Debian)",
    "Alpine": "Gói hệ điều hành (Alpine)",
}


def catalogue_xlsx(cat: Catalogue) -> None:
    wb = Workbook()
    ws = wb.active
    assert isinstance(ws, Worksheet)  # a new workbook opens on a worksheet
    ws.title = "Danh mục"
    head = [
        "STT",
        "Loại",
        "Thành phần",
        "Phiên bản",
        "Giấy phép",
        "Có trong",
        "Nguồn",
        "File giấy phép",
        "Ghi chú",
    ]
    ws.append(head)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    rows = sorted(
        cat.items.values(), key=lambda c: (KIND_ORDER.index(c.kind), c.name.lower(), c.version)
    )
    for n, c in enumerate(rows, 1):
        ws.append(
            [
                n,
                KIND_LABEL[c.kind],
                c.name,
                c.version,
                c.licence,
                ", ".join(sorted(c.images)),
                c.source,
                "\n".join(c.files),
                "Văn bản chuẩn SPDX: gói không kèm file giấy phép riêng" if c.stand_in else "",
            ]
        )
    for col, width in zip("ABCDEFGHI", [6, 22, 34, 16, 34, 30, 44, 60, 30], strict=True):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    wb.save(cat.out / "danh-muc-thanh-phan.xlsx")


README = """THÔNG BÁO GIẤY PHÉP THÀNH PHẦN BÊN THỨ BA

Thư mục này liệt kê các thành phần mã nguồn mở và mô hình AI của bên thứ ba
có trong bản triển khai, kèm văn bản giấy phép của từng thành phần.

- danh-muc-thanh-phan.xlsx: danh mục thành phần, phiên bản, giấy phép, image
  chứa thành phần, nguồn và đường dẫn tới văn bản giấy phép trong thư mục này.
- licenses/: văn bản giấy phép và file NOTICE của từng thành phần, lấy từ
  chính các gói được cài trong image. Thư mục licenses/spdx/ chứa văn bản
  chuẩn SPDX, dùng cho thành phần không kèm file giấy phép riêng (ghi rõ ở
  cột "Ghi chú" của danh mục).
- Image bên thứ ba được dùng nguyên trạng từ kho phát hành công khai; mỗi
  image mang sẵn thông báo giấy phép của các thành phần bên trong nó.

Mã nguồn của thành phần theo GPL/LGPL: các gói hệ điều hành lấy từ kho chính
thức của Debian và Alpine, đúng phiên bản ghi trong danh mục (mã nguồn tại
https://snapshot.debian.org và https://gitlab.alpinelinux.org/alpine/aports);
libvips trong gói @img/sharp-libvips-* lấy từ https://github.com/lovell/sharp-libvips
đúng phiên bản ghi trong danh mục.
Bên cung cấp sẽ cung cấp bản sao mã nguồn tương ứng khi có yêu cầu, trong
thời hạn giấy phép quy định.

Các thành phần này được sử dụng không sửa đổi, chạy như chương trình hoặc thư
viện riêng.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "third-party-notices")
    args = ap.parse_args()
    images = sorted({line.strip() for line in sys.stdin if line.strip()})
    if not images:
        sys.exit("pass the deployment's images on stdin (compose config --images)")
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    cat = Catalogue(args.out)
    for image in images:
        print(f"- {image}")
        repo = image.split(":", 1)[0]
        if repo == "dw-web":
            web_image(cat, image)
        elif repo.startswith("dw-"):
            python_image(cat, image)
        else:
            third_party_image(cat, image)
    models(cat)
    missing = spdx_texts(cat)
    catalogue_xlsx(cat)
    (args.out / "README.txt").write_text(README, encoding="utf-8")
    unknown = sorted(
        f"{c.kind} {c.name} {c.version}" for c in cat.items.values() if c.licence in {"?", ""}
    )
    print(
        f"{len(cat.items)} components; stand-in texts {sum(c.stand_in for c in cat.items.values())}"
    )
    if missing:
        print("SPDX ids with no text (check these rows by hand):", ", ".join(missing))
    if unknown:
        print("no licence declared (check by hand):", "; ".join(unknown))


if __name__ == "__main__":
    main()
