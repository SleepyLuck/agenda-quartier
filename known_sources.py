"""Which sites do we already have?  Used to keep the 'find related sites' hunt from re-finding old ones.

  python known_sources.py build                 -> writes known_sources.txt (one key per line) from every source file it can see
  python known_sources.py filter urls.txt       -> prints only the URLs that are NOT known (one URL per line in; NEW/known on stderr)
  python known_sources.py check <url>           -> 'known' or 'new' + the key it used

Key = host without 'www.'.  On SHARED hosts (instagram, facebook, eventbrite, luma, meetup, linktree, substack, teamup...)
the key also carries the account/organiser segment, so knowing one Eventbrite organiser does not hide the others.
Instagram handles in instagram_accounts.yml count as known (key instagram.com/<handle>)."""
from __future__ import annotations
import glob, re, sys
from urllib.parse import urlparse

SHARED = {
    "instagram.com": 1, "facebook.com": 1, "m.facebook.com": 1, "x.com": 1, "twitter.com": 1, "linkedin.com": 2, "bsky.app": 2,
    "eventbrite.com": 2, "eventbrite.be": 2, "eventbrite.fr": 2, "eventbrite.nl": 2, "eventbrite.co.uk": 2,
    "luma.com": 1, "lu.ma": 1, "meetup.com": 1, "linktr.ee": 1, "teamup.com": 1, "billetweb.fr": 1, "helloasso.com": 2,
    "ra.co": 2, "youtube.com": 1, "tiktok.com": 1, "mastodon.social": 1, "t.me": 1, "wordpress.com": 0, "shop.utick.net": 0,
}
SKIP_SEGMENTS = {"p", "reel", "reels", "explore", "events", "e", "o", "organizer", "organiser", "profile.php", "pages", "company", "groups", "clubs"}
FILES = ["sources.yml", "seed_sources.yml", "new_sources.yml", "all_sources.yml", "source_seeds.yml", "sources_inventory.yml",
         "instagram_accounts.yml", "manual_events.yml"]
URL_RE = re.compile(r"https?://[^\s'\"<>)\]},]+")


def key_of(url: str) -> str | None:
    u = url.strip()
    if not re.match(r"https?://", u):
        u = "https://" + u
    p = urlparse(u)
    host = (p.netloc or "").lower().split("@")[-1].split(":")[0]
    host = re.sub(r"^(www\.|m\.)", "", host) if host not in SHARED else host
    host = host[4:] if host.startswith("www.") else host
    if not host or "." not in host:
        return None
    for sh, depth in SHARED.items():
        if host == sh or host.endswith("." + sh) and sh in ("eventbrite.com", "eventbrite.be"):
            segs = [s for s in p.path.split("/") if s]
            if sh.startswith("eventbrite"):
                # only organiser pages identify a source; an event page (/e/...) says nothing about who runs it
                return f"{sh}/o/{segs[1]}" if segs[:1] == ["o"] and len(segs) > 1 else None
            if sh in ("instagram.com", "x.com", "twitter.com", "luma.com", "lu.ma", "meetup.com", "linktr.ee", "t.me", "billetweb.fr", "teamup.com"):
                segs = [s for s in segs if s.lower() not in {"p", "reel", "reels", "explore"}]
                return f"{sh}/{segs[0].lower()}" if segs else sh
            if sh in ("facebook.com", "m.facebook.com"):
                segs = [s for s in segs if s not in {"p", "pages", "groups", "events"}]
                if segs and segs[0] == "profile.php":
                    return f"facebook.com/profile.php?{p.query}"
                return f"facebook.com/{segs[0].lower()}" if segs else "facebook.com"
            if sh == "ra.co":
                return f"ra.co/{'/'.join(segs[:2])}" if len(segs) >= 2 else "ra.co"
            if sh == "linkedin.com":
                return f"linkedin.com/{'/'.join(segs[:2]).lower()}" if len(segs) >= 2 else "linkedin.com"
            if sh == "bsky.app":
                return f"bsky.app/{'/'.join(segs[:2]).lower()}" if len(segs) >= 2 else "bsky.app"
            return sh + ("/" + segs[0].lower() if segs and depth else "")
    return host


def build(root: str = ".") -> set[str]:
    keys: set[str] = set()
    for f in FILES:
        for path in glob.glob(f"{root}/{f}"):
            txt = open(path, encoding="utf-8").read()
            for m in URL_RE.findall(txt):
                k = key_of(m)
                if k:
                    keys.add(k)
            if f == "instagram_accounts.yml":
                for h in re.findall(r"handle:\s*['\"]?@?([\w.]+)", txt):
                    keys.add(f"instagram.com/{h.lower()}")
    return keys


def is_known(url: str, keys: set[str]) -> bool:
    k = key_of(url)
    return bool(k) and (k in keys or k.split("/")[0] in keys)


def main(argv):
    if len(argv) < 2:
        print(__doc__); return 2
    if argv[1] == "build":
        keys = build()
        open("known_sources.txt", "w", encoding="utf-8").write("\n".join(sorted(keys)) + "\n")
        print(f"{len(keys)} known keys -> known_sources.txt"); return 0
    keys = set(open("known_sources.txt", encoding="utf-8").read().split()) if _has("known_sources.txt") else build()
    if argv[1] == "check":
        print(("known" if is_known(argv[2], keys) else "new"), key_of(argv[2])); return 0
    if argv[1] == "filter":
        for line in open(argv[2], encoding="utf-8"):
            u = line.strip()
            if u and not is_known(u, keys):
                print(u)
        return 0
    print(__doc__); return 2


def _has(p):
    import os
    return os.path.exists(p)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
