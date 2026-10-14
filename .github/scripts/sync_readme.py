#!/usr/bin/env python3
"""Sync the dynamic blocks of the profile README.

Managed blocks (do not edit by hand -- the Action rewrites them):
  <!-- PINS:START --> ... <!-- PINS:END -->    live mirror of profile pinned repos
  <!-- LANGS:START --> ... <!-- LANGS:END -->  top languages across owned repos

Reads:
  GITHUB_TOKEN / GH_TOKEN   token with at least public read (GITHUB_TOKEN is fine)
  GITHUB_REPOSITORY         "owner/repo" (set automatically in Actions)
  PROFILE_OWNER             override for the profile owner (defaults to repo owner)
  README_PATH               path to README (defaults to README.md)

Note: under GITHUB_TOKEN the script sees public repos (+ this repo), so the
language icons reflect publicly visible work -- which is exactly what profile
viewers can see. (A personal PAT would also count private repos.)
"""

import json
import os
import re
import sys
import urllib.request

API_URL = "https://api.github.com/graphql"
PIN_CARD_BASE = "https://github-readme-stats.vercel.app/api/pin/"
SKILLICONS_BASE = "https://skillicons.dev/icons"

TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
REPO_FULL = os.environ.get("GITHUB_REPOSITORY", "hellomoinul/hellomoinul")
OWNER = os.environ.get("PROFILE_OWNER") or REPO_FULL.split("/")[0]
README_PATH = os.environ.get("README_PATH", "README.md")

MAX_PINS = 6
MAX_LANG_ICONS = 8

# Pretty card titles for known repos; anything else falls back to the repo name.
PRETTY_NAMES = {
    "niterclearanceportal": "NITER Clearance Portal",
    "voboghure-39a07f26": "Voboghure",
    "hellomoinul.github.io": "Portfolio Website",
    "fantasy_cricket_app": "Fantasy Cricket App",
    "Tax-Management-System": "Tax Management System",
}

# GitHub language name -> skillicons.dev icon id (verified against the icon list).
# Languages without an icon (Assembly, Jupyter Notebook, Markdown, ...) are skipped.
LANG_ICONS = {
    "TypeScript": "ts", "JavaScript": "js", "Python": "py",
    "C": "c", "C++": "cpp", "C#": "cs",
    "Dart": "dart", "MATLAB": "matlab", "HTML": "html", "CSS": "css",
    "Java": "java", "Go": "go", "Rust": "rust", "PHP": "php",
    "Ruby": "ruby", "Swift": "swift", "Kotlin": "kotlin", "R": "r",
    "Shell": "bash", "PowerShell": "powershell", "Lua": "lua",
    "Vue": "vue", "Svelte": "svelte", "Astro": "astro",
    "MySQL": "mysql", "PostgreSQL": "postgres", "SQLite": "sqlite",
    "MongoDB": "mongodb", "Firebase": "firebase", "Supabase": "supabase",
    "React": "react", "Flutter": "flutter", "Vite": "vite",
    "Tailwind CSS": "tailwind", "Sass": "sass", "Less": "less",
    "Dockerfile": "docker",
}


def graphql(query, variables=None):
    if not TOKEN:
        sys.exit("error: GITHUB_TOKEN (or GH_TOKEN) is not set")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "readme-sync-action",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except Exception as exc:  # noqa: BLE001 - fail loud so the workflow visibly fails
        sys.exit(f"error: GitHub API request failed: {exc}")
    if "errors" in body:
        sys.exit(f"error: GitHub API returned errors: {body['errors']}")
    return body["data"]


def fetch_pins(owner):
    data = graphql(
        """query($login: String!) {
          user(login: $login) {
            pinnedItems(first: 6, types: REPOSITORY) {
              nodes { ... on Repository { name url isFork } }
            }
          }
        }""",
        {"login": owner},
    )
    nodes = data["user"]["pinnedItems"]["nodes"]
    pins = [
        {"name": n["name"], "url": n["url"], "is_fork": n["isFork"]}
        for n in nodes
    ][:MAX_PINS]
    if not pins:
        sys.exit("error: no pinned repositories found -- refusing to wipe the section")
    return pins


def fetch_top_languages(owner):
    totals = {}
    cursor = None
    while True:
        data = graphql(
            """query($login: String!, $cursor: String) {
              user(login: $login) {
                repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
                             isArchived: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
                      edges { size node { name } }
                    }
                  }
                }
              }
            }""",
            {"login": owner, "cursor": cursor},
        )
        repos = data["user"]["repositories"]
        for node in repos["nodes"]:
            for edge in node["languages"]["edges"]:
                name = edge["node"]["name"]
                totals[name] = totals.get(name, 0) + edge["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    icons = []
    for name, _size in ranked:
        icon = LANG_ICONS.get(name)
        if icon and icon not in icons:
            icons.append(icon)
        if len(icons) >= MAX_LANG_ICONS:
            break
    if not icons:
        sys.exit("error: could not map any top language to an icon -- refusing to wipe the section")
    return icons


def pin_card(owner, pin):
    name = pin["name"]
    pretty = PRETTY_NAMES.get(name, name)
    alt = f"{pretty} (fork)" if pin["is_fork"] else pretty
    img = (
        f"{PIN_CARD_BASE}?username={owner}&repo={name}"
        "&theme=tokyonight&hide_border=true&show_owner=true"
    )
    return (
        f'  <a href="https://github.com/{owner}/{name}">\n'
        f'    <img src="{img}" alt="{alt}" />\n'
        "  </a>"
    )


def build_pins_block(owner, pins):
    cards = [pin_card(owner, p) for p in pins]
    rows = ["\n".join(cards[i:i + 2]) for i in range(0, len(cards), 2)]
    return "<div align=\"center\">\n" + "\n  <br/>\n".join(rows) + "\n</div>"


def build_langs_block(icons):
    src = f"{SKILLICONS_BASE}?i={','.join(icons)}&theme=dark"
    return (
        "<p align=\"center\">\n"
        "  <a href=\"https://skillicons.dev\">\n"
        f"    <img src=\"{src}\" alt=\"Top languages\" />\n"
        "  </a>\n"
        "</p>"
    )


def replace_block(text, marker, new_inner):
    pattern = re.compile(
        rf"(<!-- {marker}:START -->)(.*)(<!-- {marker}:END -->)", re.DOTALL
    )
    if not pattern.search(text):
        sys.exit(f"error: markers for {marker} not found in {README_PATH}")
    return pattern.sub(rf"\1\n{new_inner}\n\3", text)


def main():
    with open(README_PATH, encoding="utf-8") as fh:
        readme = fh.read()

    pins = fetch_pins(OWNER)
    print("pins:", ", ".join(p["name"] for p in pins))
    readme = replace_block(readme, "PINS", build_pins_block(OWNER, pins))

    icons = fetch_top_languages(OWNER)
    print("language icons:", ", ".join(icons))
    readme = replace_block(readme, "LANGS", build_langs_block(icons))

    with open(README_PATH, encoding="utf-8") as fh:
        original = fh.read()
    if readme != original:
        with open(README_PATH, "w", encoding="utf-8") as fh:
            fh.write(readme)
        print("README.md updated")
    else:
        print("README.md already in sync")


if __name__ == "__main__":
    main()
